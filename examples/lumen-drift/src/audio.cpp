#include "audio.h"

#include <SDL.h>

#include <cstring>

namespace {
SDL_AudioDeviceID g_dev;
SDL_AudioSpec g_spec;
std::vector<std::vector<int16_t>> g_sounds;
struct Voice { int sound = -1; size_t pos = 0; };
Voice g_voices[8];

void mix(void*, Uint8* stream, int len) {
    auto* out = reinterpret_cast<int16_t*>(stream);
    int n = len / 2;
    std::memset(stream, 0, size_t(len));
    for (auto& v : g_voices) {
        if (v.sound < 0) continue;
        const auto& s = g_sounds[size_t(v.sound)];
        for (int i = 0; i < n && v.pos < s.size(); ++i, ++v.pos) {
            int x = out[i] + s[v.pos] / 2;
            out[i] = int16_t(x > 32767 ? 32767 : x < -32768 ? -32768 : x);
        }
        if (v.pos >= s.size()) v.sound = -1;
    }
}
}  // namespace

namespace audio {

bool init() {
    if (SDL_InitSubSystem(SDL_INIT_AUDIO) != 0) return false;
    SDL_AudioSpec want{};
    want.freq = 48000;
    want.format = AUDIO_S16SYS;
    want.channels = 2;
    want.samples = 1024;
    want.callback = mix;
    g_dev = SDL_OpenAudioDevice(nullptr, 0, &want, &g_spec, 0);
    if (!g_dev) return false;
    SDL_PauseAudioDevice(g_dev, 0);
    return true;
}

void shutdown() {
    if (g_dev) SDL_CloseAudioDevice(g_dev);
    g_dev = 0;
}

int load_wav(const std::vector<uint8_t>& file) {
    if (!g_dev || file.empty()) return -1;
    SDL_AudioSpec spec;
    Uint8* buf = nullptr;
    Uint32 len = 0;
    if (!SDL_LoadWAV_RW(SDL_RWFromConstMem(file.data(), int(file.size())), 1, &spec, &buf, &len)) return -1;
    SDL_AudioCVT cvt;
    SDL_BuildAudioCVT(&cvt, spec.format, spec.channels, spec.freq, g_spec.format, g_spec.channels, g_spec.freq);
    std::vector<Uint8> tmp(size_t(len) * size_t(cvt.len_mult > 0 ? cvt.len_mult : 1));
    std::memcpy(tmp.data(), buf, len);
    SDL_FreeWAV(buf);
    cvt.buf = tmp.data();
    cvt.len = int(len);
    if (cvt.needed) SDL_ConvertAudio(&cvt);
    std::vector<int16_t> pcm(size_t(cvt.needed ? cvt.len_cvt : int(len)) / 2);
    std::memcpy(pcm.data(), tmp.data(), pcm.size() * 2);
    SDL_LockAudioDevice(g_dev);
    g_sounds.push_back(std::move(pcm));
    SDL_UnlockAudioDevice(g_dev);
    return int(g_sounds.size()) - 1;
}

void play(int id) {
    if (!g_dev || id < 0) return;
    SDL_LockAudioDevice(g_dev);
    Voice* v = &g_voices[0];
    for (auto& x : g_voices)
        if (x.sound < 0) { v = &x; break; }
    v->sound = id, v->pos = 0;
    SDL_UnlockAudioDevice(g_dev);
}

}  // namespace audio
