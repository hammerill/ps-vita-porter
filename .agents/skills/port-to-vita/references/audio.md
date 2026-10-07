# Audio

## What works on the Vita
- **SDL audio** (SDL2/SDL3 Vita ports drive SceAudio): `SDL_InitSubSystem(SDL_INIT_AUDIO)`, a callback or audio
  stream at 48000 Hz stereo S16 (the native rate; SDL converts others). The example uses SDL2 audio only, with
  vitaGL for graphics.
- **SDL_mixer** (`sdl2_mixer` in vdpm), **OpenAL Soft** (`openal-soft`), **SoLoud** (`soloud`), decoders:
  `libvorbis`, `libtremor` (integer Vorbis: cheaper on the Cortex-A9), `opusfile`, `flac`, `mpg123`, `libmodplug`,
  `libxmp`, `libopenmpt`, `libsndfile`.
- Low level: SceAudio ports directly (`sceAudioOutOpenPort`), for custom mixers.

## Replacing PC audio APIs
| Original | Vita |
|---|---|
| DirectSound, XAudio2, waveOut, WASAPI | SDL audio behind the platform layer |
| FMOD, BASS, Wwise (no homebrew Vita builds) | SDL_mixer / OpenAL Soft / SoLoud; decode the sound banks' formats with open decoders, from the user's own files |
| OpenAL (desktop) | OpenAL Soft (packaged) |
| MIDI | FluidLite / fluidsynth-lite (packaged) with a soundfont the user owns |

## Formats and memory
- Short effects: PCM WAV, 22050 Hz mono is plenty for most (a quarter of 44.1 kHz stereo). `vita assets convert`
  rule: `action = "audio"`, `format = "wav"`, `rate = 22050`, `channels = 1`.
- Music: Ogg Vorbis (or Opus), **streamed** from disk, never fully decoded into RAM (a 3-minute 44.1 kHz stereo
  track is ~30 MiB as PCM).
- Keep the PC originals in the source tree; converted files go to `build-vita/assets/`.

## Threading
SDL's audio callback runs on its own thread: keep it short, lock shared state (`SDL_LockAudioDevice`), and
remember the Vita has 3 usable cores.

## Checks
In the simulation, sound plays through the PC (same SDL code). On hardware: volume levels, crackling under load
(buffer size: 1024 samples at 48 kHz is ~21 ms), music looping, audio after suspend/resume.
