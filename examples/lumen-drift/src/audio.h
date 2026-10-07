// A small SDL2 audio mixer (PC and Vita: SDL's Vita port drives SceAudio).
#pragma once
#include <cstdint>
#include <vector>

namespace audio {
bool init();
void shutdown();
int load_wav(const std::vector<uint8_t>& file);   // converts to the device format; -1 on failure
void play(int id);
}  // namespace audio
