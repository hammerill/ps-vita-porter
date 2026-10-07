"""Analyse the game's source project for a PS Vita port. Reads files only; never builds, never decompiles.

    vita scan                       # the current repo
    vita scan path/to/game          # another source tree
    vita scan --json                # machine-readable, for agents
    vita scan --questions           # only the intake questions with recommended answers
    vita scan --assets data/        # where the game's assets are (default: vita.toml [assets] source, data/, assets/)

Reports:
  project       language(s), build system, universal-decompiler repo (DECOMP_PLAN.md, decomp/progress.json,
                platform layer), engine markers that rule a port out
  dependencies  what the code includes/links, and per library: vdpm package, build from source, replace,
                strip (online services), platform layer, or blocker (vita_porter/deps.toml)
  graphics      OpenGL version and features used (immediate mode, FBOs, VAOs, GLSL versions, instancing,
                geometry/compute shaders), SDL_Renderer, software framebuffers; Direct3D/Vulkan/Metal as blockers
  input         APIs, keys and mouse buttons used, relative mouse, wheel, gamepad, text input; the original
                control scheme (actions) as far as the code shows it
  display       hard-coded resolutions and aspect ratios, filtering (nearest vs linear)
  portability   64-bit assumptions (pointer casts, sizeof(void*) == 8, long), SSE/AVX intrinsics, inline asm,
                unaligned access; threading (APIs, thread counts); file I/O (APIs, hard-coded paths, absolute
                paths, backslashes, save locations); network features; audio APIs
  assets        inventory with sizes, texture formats and resolutions, audio formats; a RAM/VRAM estimate
                against the Vita budget (256 MiB MAIN with a 128 MiB default newlib heap, 112 MiB CDRAM)
  intake        the questions to ask the user, each with a recommended answer grounded in the above

Exit code 1 when the project can't be ported as is (no C/C++ source, an engine without a Vita runtime, no
build at all): tell the user why; if the source is incomplete, point them to universal-decompiler.
"""
from __future__ import annotations

import json
import os
import re
import tomllib
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from vita_porter.common import OK, PROBLEM, emit_json, find_project, human, is_ud_repo, load_config, usage
from vita_porter.images import sniff

MAX_FILES = 40_000
MAX_SOURCE_BYTES = 2 << 20
SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "build", "build-vita", "build-sim", "out", "_deps",
             ".cache", ".idea", ".vs", ".vscode", "cmake-build-debug", "cmake-build-release", "decomp", "ghidra", "pyghidra_mcp_projects"}
ASSET_DIR_NAMES = ("data", "assets", "res", "resources", "content", "media", "gfx", "game")
C_EXT = {".c", ".cc", ".cpp", ".cxx", ".c++", ".h", ".hh", ".hpp", ".hxx", ".inl", ".ipp"}
LANG_EXT = {".cs": "C#", ".java": "Java", ".kt": "Kotlin", ".rs": "Rust", ".go": "Go", ".py": "Python", ".gd": "GDScript",
            ".lua": "Lua", ".js": "JavaScript", ".ts": "TypeScript", ".swift": "Swift", ".m": "Objective-C", ".mm": "Objective-C++",
            ".hx": "Haxe", ".nim": "Nim", ".zig": "Zig", ".d": "D", ".pas": "Pascal"}
SHADER_EXT = {".glsl", ".vert", ".frag", ".vs", ".fs", ".vsh", ".fsh", ".shader", ".hlsl", ".fx", ".cg", ".geom", ".comp"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tga", ".bmp", ".gif", ".dds", ".ktx", ".webp"}
AUDIO_EXT = {".wav", ".ogg", ".mp3", ".flac", ".opus", ".mod", ".xm", ".s3m", ".it", ".mid", ".midi", ".aiff", ".wma"}
VIDEO_EXT = {".mp4", ".bik", ".bk2", ".ogv", ".webm", ".avi", ".wmv", ".mpg", ".mpeg"}
ARCHIVE_EXT = {".pak", ".pk3", ".zip", ".wad", ".dat", ".bin", ".arc", ".big", ".grp", ".rpa", ".pck", ".vpp"}
DEPS = Path(__file__).resolve().parent / "deps.toml"

# Vita budgets (see skills/port-to-vita/references/memory.md)
MAIN_MB, MAIN_EXT_MB, HEAP_MB, CDRAM_MB, PHYCONT_MB = 256, 365, 128, 112, 26
VITA_W, VITA_H = 960, 544
BUTTONS = ["Cross", "Circle", "Square", "Triangle", "L", "R", "Start", "Select", "D-pad Up", "D-pad Down", "D-pad Left", "D-pad Right"]

ENGINE_MARKERS = [
    ("Unity", ["ProjectSettings/ProjectVersion.txt", "Assets/*.unity", "*/Assets/*.unity"], "C#/Unity has no Vita runtime available to homebrew"),
    ("Unreal Engine", ["*.uproject"], "Unreal has no Vita runtime available to homebrew"),
    ("Godot", ["project.godot"], "Godot has no maintained Vita export for homebrew (check the community before refusing outright)"),
    ("GameMaker", ["*.yyp"], "GameMaker has no Vita runtime available to homebrew"),
    ("MonoGame/XNA/FNA", ["*.csproj"], "C#/.NET has no Vita runtime available to homebrew"),
    ("Ren'Py", ["game/script.rpy", "renpy/__init__.py"], "Ren'Py is Python; it has its own community Vita efforts, not a C/C++ port"),
    ("RPG Maker MV/MZ", ["js/rpg_core.js", "www/js/rpg_core.js", "js/rmmz_core.js"], "an HTML5 engine (EasyRPG-style runtimes are separate projects)"),
    ("Java/LWJGL", ["build.gradle", "pom.xml", "build.gradle.kts"], "the JVM has no Vita runtime available to homebrew"),
]

# --------------------------------------------------------------------------- regexes over C/C++ source

INCLUDE_RX = re.compile(r'^\s*#\s*include\s*[<"]([^>"]+)[>"]', re.M)
FIND_PACKAGE_RX = re.compile(r"find_package\s*\(\s*([A-Za-z0-9_]+)", re.I)
GL_FEATURES = {
    "immediate mode (glBegin/glEnd)": r"\bglBegin\s*\(",
    "client arrays (glVertexPointer)": r"\bgl(Vertex|TexCoord|Color)Pointer\s*\(",
    "display lists": r"\bgl(NewList|CallList)\s*\(",
    "framebuffer objects": r"\bgl(Gen|Bind)Framebuffers?(EXT)?\s*\(",
    "vertex buffer objects": r"\bgl(Gen|Bind)Buffers?(ARB)?\s*\(",
    "vertex array objects": r"\bgl(Gen|Bind)VertexArrays?\s*\(",
    "GLSL shaders": r"\bgl(ShaderSource|CompileShader|CreateProgram)(ARB)?\s*\(",
    "instancing": r"\bglDraw(Arrays|Elements)Instanced\w*\s*\(",
    "geometry/tessellation shaders": r"\bGL_(GEOMETRY|TESS_CONTROL|TESS_EVALUATION)_SHADER\b",
    "compute shaders": r"\bglDispatchCompute\s*\(|\bGL_COMPUTE_SHADER\b",
    "buffer mapping": r"\bglMap(Buffer|BufferRange)\s*\(",
    "multiple render targets": r"\bglDrawBuffers\s*\(",
    "texture arrays / 3D textures": r"\bGL_TEXTURE_(2D_ARRAY|3D)\b",
    "glReadPixels": r"\bglReadPixels\s*\(",
}
GL_RISKY = {"display lists", "geometry/tessellation shaders", "compute shaders", "buffer mapping", "multiple render targets",
            "texture arrays / 3D textures", "instancing", "vertex array objects"}
OTHER_GFX = {
    "SDL_Renderer": r"\bSDL_(CreateRenderer|RenderCopy|RenderTexture|RenderPresent)\b",
    "software framebuffer (SDL surfaces/streaming textures)": r"\bSDL_(UpdateTexture|LockTexture|BlitSurface|UpdateWindowSurface|GetWindowSurface)\b",
    "SDL GL context": r"\bSDL_GL_(CreateContext|SetAttribute|SwapWindow)\b",
    "GLFW window": r"\bglfwCreateWindow\b",
    "Direct3D": r"\b(IDirect3D(9|Device9)|ID3D1[012]\w*|D3D1[12]CreateDevice|Direct3DCreate9)\b",
    "Vulkan": r"\bvk(CreateInstance|CreateDevice|QueueSubmit)\b",
}
GL_VERSION_RXS = [
    re.compile(r"SDL_GL_CONTEXT_MAJOR_VERSION\s*,\s*(\d)"),
    re.compile(r"GLFW_CONTEXT_VERSION_MAJOR\s*,\s*(\d)"),
]
GLSL_VERSION_RX = re.compile(r"#\s*version\s+(\d{3})(\s+(core|es|compatibility))?")
KEY_RXS = [
    ("sdl", re.compile(r"\bSDL_SCANCODE_([A-Z0-9_]+)\b")),
    ("sdl", re.compile(r"\bSDLK_([A-Za-z0-9_]+)\b")),
    ("glfw", re.compile(r"\bGLFW_KEY_([A-Z0-9_]+)\b")),
    ("win32", re.compile(r"\bVK_([A-Z0-9_]+)\b")),
    ("dinput", re.compile(r"\bDIK_([A-Z0-9_]+)\b")),
]
INPUT_API = {
    "SDL keyboard": r"\bSDL_(KEYDOWN|KEYUP|EVENT_KEY_DOWN|GetKeyboardState)\b",
    "SDL mouse": r"\bSDL_(MOUSEBUTTONDOWN|MOUSEMOTION|EVENT_MOUSE_BUTTON_DOWN|EVENT_MOUSE_MOTION|GetMouseState)\b",
    "SDL gamepad": r"\bSDL_(GameController\w+|Gamepad\w+|CONTROLLERBUTTONDOWN|EVENT_GAMEPAD_BUTTON_DOWN|JoystickOpen|OpenJoystick)\b",
    "GLFW input": r"\bglfw(GetKey|SetKeyCallback|GetMouseButton|SetCursorPosCallback)\b",
    "Win32 input": r"\b(GetAsyncKeyState|GetKeyState|WM_KEYDOWN|WM_LBUTTONDOWN|WM_MOUSEMOVE|RegisterRawInputDevices)\b",
    "DirectInput": r"\b(DirectInput8Create|IDirectInputDevice8)\b",
    "XInput": r"\bXInputGetState\b",
}
MOUSE = {
    "buttons": r"\b(SDL_BUTTON_(LEFT|RIGHT|MIDDLE)|GLFW_MOUSE_BUTTON_\w+|WM_[LRM]BUTTONDOWN|MK_[LR]BUTTON)\b",
    "relative": r"\b(SDL_SetRelativeMouseMode|SDL_SetWindowRelativeMouseMode|GLFW_CURSOR_DISABLED|ClipCursor|SetCursorPos)\b",
    "wheel": r"\b(SDL_MOUSEWHEEL|SDL_EVENT_MOUSE_WHEEL|glfwSetScrollCallback|WM_MOUSEWHEEL)\b",
    "cursor drawn": r"\b(SDL_ShowCursor|ShowCursor|glfwSetCursor)\b",
}
TEXT_INPUT_RX = r"\b(SDL_StartTextInput|SDL_TEXTINPUT|SDL_EVENT_TEXT_INPUT|glfwSetCharCallback|WM_CHAR)\b"
RES_PAIR_RX = re.compile(r"\b(\d{3,4})\s*(?:,|x|\*|×)\s*(\d{3,4})\b")
RES_DEFINE_RX = re.compile(r"(?:#\s*define|constexpr|const|static|enum\s*\{?)\s*[\w\s]*?\b(\w*?(?:WIDTH|_W|Width|WIDTH_\w*))\s*=?\s*(\d{3,4})\b")
RES_DEFINE_H_RX = re.compile(r"(?:#\s*define|constexpr|const|static|enum\s*\{?)\s*[\w\s]*?\b(\w*?(?:HEIGHT|_H|Height|HEIGHT_\w*))\s*=?\s*(\d{3,4})\b")
WIDTHS = {256, 320, 384, 400, 426, 480, 512, 640, 720, 800, 854, 960, 1024, 1152, 1280, 1360, 1366, 1440, 1600, 1680, 1920, 2560, 3840}
HEIGHTS = {192, 200, 224, 240, 256, 270, 272, 288, 300, 320, 360, 384, 400, 448, 480, 540, 544, 576, 600, 720, 768, 800, 864, 900, 960,
           1024, 1050, 1080, 1200, 1440, 2160}
NEAREST_RX = r"\b(GL_NEAREST|SDL_SCALEMODE_NEAREST|SDL_ScaleModeNearest)\b|SDL_HINT_RENDER_SCALE_QUALITY\s*,\s*\"(0|nearest)\""
LINEAR_RX = r"\b(GL_LINEAR(_MIPMAP_\w+)?|SDL_SCALEMODE_LINEAR|SDL_ScaleModeLinear)\b"
PORTABILITY = {
    "pointer size assumed 8": (r"sizeof\s*\(\s*(void\s*\*|size_t|intptr_t|uintptr_t|long)\s*\)\s*==\s*8", "64-bit"),
    "64-bit platform macros": (r"\b(_WIN64|__x86_64__|__amd64__|_M_X64|__LP64__|__aarch64__)\b", "64-bit"),
    "pointer cast to a 32/64-bit integer type": (r"reinterpret_cast\s*<\s*(int|unsigned|unsigned int|long|DWORD|uint32_t|u32|int32_t|uint64_t|u64|int64_t|long long|unsigned long)\s*>", "64-bit"),
    "C cast of an address to an integer": (r"\(\s*(int|unsigned int|DWORD|uint32_t|u32|long|unsigned long|uint64_t|int64_t)\s*\)\s*(&\w|\w+_?ptr\b|\(void\s*\*\))", "64-bit"),
    "x86 SIMD intrinsics": (r"#\s*include\s*<(xmm|emm|pmm|tmm|smm|nmm|wmm|imm|ammint|avx\w*|x86)intrin\.h>|#\s*include\s*<intrin\.h>|\b_mm(256|512)?_\w+\s*\(|\b__m(128|256|512)[di]?\b", "simd"),
    "inline assembly": (r"\b(__asm\b|__asm__|_asm\b|asm\s+volatile|asm\s*\()", "asm"),
    "unaligned typed loads from byte buffers": (r"\*\s*\(\s*(const\s+)?(float|double|uint64_t|int64_t|u64|s64|long long)\s*\*\s*\)\s*\(?\s*\w*(buf|data|ptr|p|bytes)\w*\s*\+", "alignment"),
    "packed structs": (r"#\s*pragma\s+pack|__attribute__\s*\(\(\s*packed", "alignment"),
}
THREAD_API = {
    "std::thread": r"\bstd::(thread|jthread)\b", "std::async": r"\bstd::async\b", "pthreads": r"\bpthread_create\b",
    "SDL threads": r"\bSDL_CreateThread\b", "Win32 threads": r"\b(CreateThread|_beginthreadex)\b", "OpenMP": r"#\s*pragma\s+omp\b",
    "thread count from the CPU": r"\b(hardware_concurrency|SDL_GetCPUCount|SDL_GetNumLogicalCPUCores|GetSystemInfo)\b",
}
FILE_API = {
    "stdio": r"\bfopen\s*\(", "iostreams": r"\bstd::(i|o)?fstream\b", "SDL RWops/IOStream": r"\bSDL_(RWFromFile|IOFromFile|LoadFile)\b",
    "Win32 files": r"\bCreateFile[AW]?\s*\(", "POSIX": r"\b(open|opendir|readdir|stat)\s*\(", "std::filesystem": r"\bstd::filesystem\b",
    "PhysicsFS": r"\bPHYSFS_\w+\b",
}
PATH_HINTS = {
    "base path / pref path": r"\bSDL_Get(Base|Pref)Path\b|\bGetModuleFileName\w*\b|\bSHGetFolderPath\w*\b|\bSHGetKnownFolderPath\b",
    "environment (HOME/APPDATA/...)": r"getenv\s*\(\s*\"(HOME|APPDATA|LOCALAPPDATA|USERPROFILE|XDG_\w+)\"",
    "changes directory": r"\b(_?chdir|SetCurrentDirectory\w*)\s*\(",
}
STRING_RX = re.compile(r'"((?:[^"\\\n]|\\.){2,200})"')
SAVE_RX = re.compile(r"\b(save|sav|savegame|config|settings|options|profile|highscore|scores?)\b", re.I)
NETWORK = {
    "BSD/Win sockets": r"\b(WSAStartup|socket\s*\(|connect\s*\(|getaddrinfo)\b", "libcurl": r"\bcurl_easy_\w+",
    "SDL_net": r"\bSDLNet_\w+", "ENet": r"\benet_host_\w+", "Steamworks": r"\bSteam(API_Init|User|Friends|UserStats|Networking)\b",
    "Discord": r"\bDiscord_(Initialize|UpdatePresence)\b|\bdiscord::Core\b", "HTTP URLs": r"\"https?://",
}
AUDIO_API = {
    "SDL audio": r"\bSDL_(OpenAudio|OpenAudioDevice|OpenAudioDeviceStream|QueueAudio|PutAudioStreamData)\b", "SDL_mixer": r"\bMix_\w+\s*\(",
    "OpenAL": r"\bal(GenSources|SourcePlay|BufferData)\s*\(", "FMOD": r"\bFMOD_\w+|FMOD::", "BASS": r"\bBASS_\w+\s*\(",
    "XAudio2/DirectSound": r"\b(XAudio2Create|DirectSoundCreate8?)\b", "waveOut": r"\bwaveOut\w+\s*\(",
}
QUIT_RX = r"\b(SDL_QUIT|SDL_EVENT_QUIT|PostQuitMessage|glfwSetWindowShouldClose|exit\s*\(\s*0\s*\))|\"(Quit|Exit|Quit Game|Exit Game|Quit to Desktop)\""
GENRES = {
    "shooter": r"\b(shoot|bullet|weapon|ammo|reload|aim|crosshair|gun|projectile)\w*",
    "platformer": r"\b(jump|platformer|ledge|coyote|double_?jump|wall_?slide)\w*",
    "rpg": r"\b(quest|inventory|dialog(ue)?|npc|party|spell|equip|experience|xp|level_?up)\w*",
    "racing": r"\b(lap|race|car|kart|vehicle|steer|throttle|checkpoint)\w*",
    "puzzle": r"\b(puzzle|match3|tile|swap|grid|block|piece)\w*",
    "strategy": r"\b(unit|turn|build(ing)?|resource|army|tech_?tree|selection_?box)\w*",
    "fighting": r"\b(combo|hitbox|special_?move|fighter|round)\w*",
    "adventure": r"\b(point_?and_?click|verb|hotspot|inventory_?item|scene)\w*",
}


@lru_cache(maxsize=1)
def deps_table() -> dict:
    return tomllib.loads(DEPS.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- walking

def is_build_tree(d: Path) -> bool:
    """A CMake build folder (or one of the kit's): never part of the game's source."""
    return (d / "CMakeCache.txt").exists() or (d / "vita-build.log").exists() or (d / ".vita-backend").exists()


def is_kit(d: Path) -> bool:
    """The vitaport kit copied by `vita init --kit`: the port's own code, not the game's."""
    return (d / "vitaport.h").exists() and (d / "vitaport_sim.c").exists()


def walk(root: Path, skip_rel: set[str]) -> list[Path]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        relp = Path(dirpath).relative_to(root).as_posix()
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and (relp + "/" + d if relp != "." else d) not in skip_rel
                       and not is_build_tree(Path(dirpath) / d) and not is_kit(Path(dirpath) / d)]
        for fn in filenames:
            out.append(Path(dirpath) / fn)
            if len(out) >= MAX_FILES:
                return out
    return out


def read(p: Path) -> str:
    try:
        if p.stat().st_size > MAX_SOURCE_BYTES:
            return ""
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def strip_comments(s: str) -> str:
    s = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), s, flags=re.S)
    return re.sub(r"//[^\n]*", "", s)


class Hits:
    """Counts and first locations of regex hits across files."""

    def __init__(self):
        self.count: Counter = Counter()
        self.where: dict[str, list[str]] = defaultdict(list)

    def add(self, key: str, path: str, text: str, rx: str | re.Pattern, flags=0):
        pat = rx if isinstance(rx, re.Pattern) else re.compile(rx, flags)
        for m in pat.finditer(text):
            self.count[key] += 1
            if len(self.where[key]) < 3:
                self.where[key].append(f"{path}:{text.count(chr(10), 0, m.start()) + 1}")

    def report(self) -> list[dict]:
        return [dict(name=k, count=c, where=self.where[k]) for k, c in self.count.most_common()]


# --------------------------------------------------------------------------- analysis

def detect_project(root: Path, files: list[Path]) -> dict:
    exts = Counter(p.suffix.lower() for p in files)
    c_files = sum(exts[e] for e in C_EXT)
    langs = {"C/C++": c_files} if c_files else {}
    for e, lang in LANG_EXT.items():
        if exts[e]:
            langs[lang] = langs.get(lang, 0) + exts[e]
    rels = [p.relative_to(root).as_posix() for p in files]
    import fnmatch
    engines = []
    for name, pats, why in ENGINE_MARKERS:
        hit = next((r for r in rels for pat in pats if fnmatch.fnmatch(r, pat)), None)
        if hit and not (name == "Java/LWJGL" and c_files > exts[".java"]):
            engines.append(dict(name=name, evidence=hit, why=why))
    builds = []
    for marker, label in (("CMakeLists.txt", "CMake"), ("Makefile", "Make"), ("makefile", "Make"), ("meson.build", "Meson"),
                          ("premake5.lua", "Premake"), ("premake4.lua", "Premake"), ("SConstruct", "SCons"), ("configure.ac", "Autotools"),
                          ("configure", "Autotools"), ("BUILD.bazel", "Bazel"), ("WORKSPACE", "Bazel"), ("Cargo.toml", "Cargo"),
                          ("build.gradle", "Gradle"), ("xmake.lua", "xmake")):
        if (root / marker).exists():
            builds.append(label)
    if any(r.endswith((".sln", ".vcxproj")) for r in rels):
        builds.append("Visual Studio")
    if any(r.endswith(".xcodeproj/project.pbxproj") for r in rels):
        builds.append("Xcode")
    builds = list(dict.fromkeys(builds))
    ud = is_ud_repo(root)
    out: dict = dict(root=str(root), languages=langs, c_files=c_files, build_systems=builds, cmake="CMake" in builds, ud_repo=ud, engines=engines)
    if ud:
        u: dict = dict(decomp_plan=(root / "DECOMP_PLAN.md").exists(), decomplog=(root / "DECOMPLOG.md").exists())
        prog = root / "decomp" / "progress.json"
        if prog.exists():
            try:
                fns = json.loads(prog.read_text(encoding="utf-8")).get("functions", [])
                st = Counter(f.get("status", "?") for f in fns)
                u["functions"] = dict(total=len(fns), **st)
                todo = sum(st[s] for s in ("todo", "unknown", "reversed", "?"))
                u["incomplete"] = todo
            except (ValueError, OSError) as e:
                u["progress_error"] = str(e)
        plan = root / "DECOMP_PLAN.md"
        if plan.exists():
            txt = plan.read_text(encoding="utf-8", errors="replace")
            done = re.findall(r"^- \[( |x|X)\] (.+)$", txt, re.M)
            u["done_criterion"] = [dict(done=d.lower() == "x", item=i.strip()) for d, i in done[:12]]
        for cand in ("src/platform", "platform", "source/platform"):
            if (root / cand).is_dir():
                u["platform_layer"] = cand
                u["platform_backends"] = sorted(p.name for p in (root / cand).iterdir() if p.is_file())
                break
        try:
            u["ud_toml"] = tomllib.loads((root / "ud.toml").read_text(encoding="utf-8")) if (root / "ud.toml").exists() else {}
        except tomllib.TOMLDecodeError:
            u["ud_toml"] = {}
        out["ud"] = u
    return out


def scan_sources(root: Path, files: list[Path]) -> dict:
    src = [p for p in files if p.suffix.lower() in C_EXT]
    cm = [p for p in files if p.name == "CMakeLists.txt" or p.suffix == ".cmake"]
    shaders = [p for p in files if p.suffix.lower() in SHADER_EXT]
    inc_counter: Counter = Counter()
    fp_counter: Counter = Counter()
    H = {k: Hits() for k in ("gl", "gfx", "keys", "input", "mouse", "port", "thread", "file", "path", "net", "audio", "genre", "misc")}
    res_pairs: Counter = Counter()
    res_where: dict = {}
    widths, heights = Counter(), Counter()
    glsl: Counter = Counter()
    gl_major: Counter = Counter()
    strings_paths, strings_saves = Counter(), Counter()
    nearest = linear = 0
    text_input = Hits()
    quit_h = Hits()
    key_by_api: dict[str, Counter] = defaultdict(Counter)
    actions_enum: list[str] = []
    for p in src:
        rp = p.relative_to(root).as_posix()
        raw = read(p)
        if not raw:
            continue
        t = strip_comments(raw)
        for inc in INCLUDE_RX.findall(raw):
            inc_counter[inc] += 1
        for k, rx in GL_FEATURES.items():
            H["gl"].add(k, rp, t, rx)
        for k, rx in OTHER_GFX.items():
            H["gfx"].add(k, rp, t, rx)
        for rx in GL_VERSION_RXS:
            for m in rx.finditer(t):
                gl_major[m.group(1)] += 1
        for m in GLSL_VERSION_RX.finditer(raw):
            glsl[m.group(1) + (" " + m.group(3) if m.group(3) else "")] += 1
        for api, rx in KEY_RXS:
            for m in rx.finditer(t):
                key_by_api[api][m.group(1).upper()] += 1
        for k, rx in INPUT_API.items():
            H["input"].add(k, rp, t, rx)
        for k, rx in MOUSE.items():
            H["mouse"].add(k, rp, t, rx)
        text_input.add("text input", rp, t, TEXT_INPUT_RX)
        quit_h.add("quit", rp, raw, QUIT_RX)
        for k, (rx, _cat) in PORTABILITY.items():
            H["port"].add(k, rp, t, rx)
        for k, rx in THREAD_API.items():
            H["thread"].add(k, rp, t, rx)
        for k, rx in FILE_API.items():
            H["file"].add(k, rp, t, rx)
        for k, rx in PATH_HINTS.items():
            H["path"].add(k, rp, t, rx)
        for k, rx in NETWORK.items():
            H["net"].add(k, rp, raw if k == "HTTP URLs" else t, rx)
        for k, rx in AUDIO_API.items():
            H["audio"].add(k, rp, t, rx)
        for k, rx in GENRES.items():
            H["genre"].add(k, rp, raw.lower(), rx)
        nearest += len(re.findall(NEAREST_RX, t))
        linear += len(re.findall(LINEAR_RX, t))
        for m in RES_PAIR_RX.finditer(t):
            w, h = int(m.group(1)), int(m.group(2))
            if w in WIDTHS and h in HEIGHTS and w > h:
                res_pairs[(w, h)] += 1
                res_where.setdefault((w, h), f"{rp}:{t.count(chr(10), 0, m.start()) + 1}")
        for m in RES_DEFINE_RX.finditer(t):
            if int(m.group(2)) in WIDTHS:
                widths[int(m.group(2))] += 1
        for m in RES_DEFINE_H_RX.finditer(t):
            if int(m.group(2)) in HEIGHTS:
                heights[int(m.group(2))] += 1
        for s in STRING_RX.findall(raw):
            if ("/" in s or "\\\\" in s) and re.search(r"\.\w{2,4}$|^(\.{1,2}/|data/|assets/|res/|[A-Za-z]:\\\\)", s) and " " not in s.strip()[:1]:
                strings_paths[s] += 1
            if SAVE_RX.search(s) and len(s) < 60 and re.search(r"\.\w{2,4}$|/", s):
                strings_saves[s] += 1
        m = re.search(r"enum\s+(?:class\s+)?(?:Key|Action|Button|InputAction|GameAction)\s*(?::\s*\w+\s*)?\{([^}]*)\}", t)
        if m and not actions_enum:
            actions_enum = [a.split("=")[0].strip() for a in m.group(1).split(",") if a.strip() and a.split("=")[0].strip() not in ("Count", "COUNT", "Max", "MAX", "Num", "NUM")]
    for p in shaders:
        for m in GLSL_VERSION_RX.finditer(read(p)):
            glsl[m.group(1) + (" " + m.group(3) if m.group(3) else "")] += 1
    for p in cm:
        for m in FIND_PACKAGE_RX.finditer(read(p)):
            fp_counter[m.group(1)] += 1
    # derive pairs from WIDTH/HEIGHT constants when there are no literal pairs
    if not res_pairs and widths and heights:
        w, h = widths.most_common(1)[0][0], heights.most_common(1)[0][0]
        if w > h:
            res_pairs[(w, h)] += 1
            res_where[(w, h)] = "WIDTH/HEIGHT constants"
    return dict(includes=inc_counter, find_package=fp_counter, hits=H, res_pairs=res_pairs, res_where=res_where, glsl=glsl,
                gl_major=gl_major, nearest=nearest, linear=linear, text_input=text_input, quit=quit_h, keys=key_by_api,
                actions_enum=actions_enum, strings_paths=strings_paths, strings_saves=strings_saves, shader_files=len(shaders),
                source_files=len(src))


def match_deps(includes: Counter, find_package: Counter) -> list[dict]:
    table = deps_table()["deps"]
    out = []
    for key, d in table.items():
        ev = []
        for rx in d.get("includes", []):
            pat = re.compile(rx)
            hits = [i for i in includes if pat.search(i)]
            if hits:
                ev.append("#include " + ", ".join(sorted(hits)[:3]))
        for name in d.get("cmake", []):
            if find_package.get(name):
                ev.append(f"find_package({name})")
        if ev:
            out.append(dict(id=key, name=d["name"], status=d["status"], vdpm=d.get("vdpm"), replacement=d.get("replacement"),
                            note=d.get("note"), evidence="; ".join(ev)))
    # the generic SDL.h include means SDL2 unless SDL3/SDL1 is evident
    ids = {x["id"] for x in out}
    if any(re.fullmatch(r"SDL\.h", i) for i in includes) and not ids & {"sdl2", "sdl3", "sdl12"}:
        d = table["sdl2"]
        out.append(dict(id="sdl2", name=d["name"], status=d["status"], vdpm=d["vdpm"], replacement=None, note=d.get("note"),
                        evidence="#include \"SDL.h\" (SDL2 assumed)"))
    order = {"blocker": 0, "platform-layer": 1, "replace": 2, "strip": 3, "build": 4, "available": 5, "header-only": 6}
    out.sort(key=lambda x: (order.get(x["status"], 9), x["name"].lower()))
    return out


def asset_inventory(adir: Path | None, max_files: int = 20000) -> dict:
    if not adir or not adir.is_dir():
        return dict(dir=str(adir) if adir else None, found=False)
    by_type: Counter = Counter()
    sizes: Counter = Counter()
    tex = dict(count=0, decoded_bytes=0, max_side=0, over_2048=[], over_4096=[], formats=Counter(), small=0, sides=[])
    audio = dict(count=0, bytes=0, formats=Counter(), wav_bytes=0)
    videos, archives = [], []
    n = total = 0
    for p in adir.rglob("*"):
        if not p.is_file():
            continue
        n += 1
        if n > max_files:
            break
        sz = p.stat().st_size
        total += sz
        ext = p.suffix.lower()
        kind = ("image" if ext in IMAGE_EXT else "audio" if ext in AUDIO_EXT else "video" if ext in VIDEO_EXT else
                "archive" if ext in ARCHIVE_EXT else "other")
        by_type[kind] += 1
        sizes[kind] += sz
        rp = p.relative_to(adir).as_posix()
        if kind == "image":
            s = sniff(p)
            if s and s.get("width") and s.get("height"):
                w, h = s["width"], s["height"]
                tex["count"] += 1
                tex["formats"][s["format"] + (f" {s['compressed']}" if s.get("compressed") else "")] += 1
                comp = s.get("compressed")
                tex["decoded_bytes"] += w * h * (1 if comp and "DXT" in str(comp) else 4)
                tex["max_side"] = max(tex["max_side"], w, h)
                tex["sides"].append(max(w, h))
                if max(w, h) > 4096:
                    tex["over_4096"].append(f"{rp} {w}x{h}")
                elif max(w, h) > 2048:
                    tex["over_2048"].append(f"{rp} {w}x{h}")
                if max(w, h) <= 256:
                    tex["small"] += 1
        elif kind == "audio":
            audio["count"] += 1
            audio["bytes"] += sz
            audio["formats"][ext[1:]] += 1
            if ext == ".wav":
                audio["wav_bytes"] += sz
        elif kind == "video":
            videos.append(rp)
        elif kind == "archive":
            archives.append(f"{rp} ({human(sz)})")
    sides = sorted(tex.pop("sides"))
    tex["median_side"] = sides[len(sides) // 2] if sides else 0
    tex["formats"] = dict(tex["formats"])
    audio["formats"] = dict(audio["formats"])
    tex["over_2048"], tex["over_4096"] = tex["over_2048"][:20], tex["over_4096"][:20]
    # resident estimate: every texture decoded + uncompressed audio + compressed audio x1 (streamed music) + other data
    other = sizes["other"] + sizes["archive"]
    est_vram = tex["decoded_bytes"]
    est_ram = audio["wav_bytes"] + (audio["bytes"] - audio["wav_bytes"]) + other
    return dict(dir=str(adir), found=True, files=n, truncated=n > max_files, total_bytes=total, by_type=dict(by_type),
                bytes_by_type=dict(sizes), textures=tex, audio=audio, videos=videos[:20], archives=archives[:20],
                estimate=dict(texture_bytes=est_vram, other_ram_bytes=est_ram, cdram_budget=CDRAM_MB << 20, heap_budget=HEAP_MB << 20,
                              main_budget=MAIN_MB << 20, textures_over_cdram=est_vram > (CDRAM_MB << 20),
                              ram_over_heap=est_ram > (HEAP_MB << 20)))


def pick_asset_dir(root: Path, cfg: dict, override: str | None) -> Path | None:
    if override:
        return Path(override) if Path(override).is_absolute() else root / override
    src = cfg.get("assets", {}).get("source")
    if src and (root / src).is_dir():
        return root / src
    for d in ASSET_DIR_NAMES:
        if (root / d).is_dir():
            return root / d
    return None


def keys_report(keys: dict[str, Counter]) -> list[dict]:
    merged: Counter = Counter()
    for api, c in keys.items():
        for k, n in c.items():
            merged[(api, k)] += n
    return [dict(api=a, key=k, count=n) for (a, k), n in merged.most_common(60)]


def genre_guess(h: Hits) -> dict:
    scores = h.count
    if not scores:
        return dict(guess="unknown", scores={})
    top = scores.most_common(3)
    best, n = top[0]
    second = top[1][1] if len(top) > 1 else 0
    return dict(guess=best if n >= 5 and n >= 1.5 * second else "unclear", scores=dict(top))


def scan(path: str | Path | None = None, asset_dir: str | None = None) -> dict:
    root = Path(path) if path else (find_project() or Path.cwd())
    root = root.resolve()
    if not root.is_dir():
        usage(f"no such folder: {root}")
    cfg = load_config(root)
    adir = pick_asset_dir(root, cfg, asset_dir)
    skip = set()
    if adir and adir.is_relative_to(root):
        skip.add(adir.relative_to(root).as_posix())
    files = walk(root, skip)
    proj = detect_project(root, files)
    s = scan_sources(root, files)
    deps = match_deps(s["includes"], s["find_package"])
    H = s["hits"]
    gl = H["gl"].report()
    gfx = H["gfx"].report()
    gfx_names = {x["name"] for x in gfx}
    uses_gl = any(d["id"] in ("opengl", "gles", "glew", "glad") for d in deps) or bool(gl)
    risky = [x for x in gl if x["name"] in GL_RISKY]
    glsl = dict(s["glsl"].most_common())
    gl_major = s["gl_major"].most_common(1)[0][0] if s["gl_major"] else None
    api = ("Direct3D" if "Direct3D" in gfx_names or any(d["id"] == "d3d" for d in deps) else
           "Vulkan" if "Vulkan" in gfx_names or any(d["id"] == "vulkan" for d in deps) else
           "OpenGL" if uses_gl else "SDL_Renderer" if "SDL_Renderer" in gfx_names else
           "software" if "software framebuffer (SDL surfaces/streaming textures)" in gfx_names else "unknown")
    summary = api + (f" {gl_major}.x context" if gl_major else "") + (f", GLSL {', '.join(glsl)}" if glsl else "")
    graphics = dict(api=api, summary=summary, gl_features=gl, other=gfx, glsl_versions=glsl, gl_context_major=gl_major,
                    risky=[x["name"] for x in risky], shader_files=s["shader_files"], nearest_filter_uses=s["nearest"], linear_filter_uses=s["linear"])
    keys = keys_report(s["keys"])
    mouse = {x["name"]: x for x in H["mouse"].report()}
    inp = dict(apis=H["input"].report(), keys=keys, distinct_keys=len({k["key"] for k in keys}), mouse=mouse,
               mouse_used=bool(mouse), relative_mouse="relative" in mouse, wheel="wheel" in mouse,
               gamepad=any(x["name"] in ("SDL gamepad", "XInput") for x in H["input"].report()),
               text_input=s["text_input"].report(), actions_enum=s["actions_enum"])
    pairs = [dict(width=w, height=h, aspect=round(w / h, 3), count=c, where=s["res_where"].get((w, h)))
             for (w, h), c in s["res_pairs"].most_common(8)]
    display = dict(resolutions=pairs, original=pairs[0] if pairs else None, vita=dict(width=VITA_W, height=VITA_H, aspect=round(VITA_W / VITA_H, 3)))
    port = H["port"].report()
    cats = defaultdict(list)
    for x in port:
        cats[PORTABILITY[x["name"]][1]].append(x)
    portability = dict(sixty_four_bit=cats["64-bit"], simd=cats["simd"], asm=cats["asm"], alignment=cats["alignment"])
    threads = dict(apis=H["thread"].report())
    files_io = dict(apis=H["file"].report(), hints=H["path"].report(),
                    paths=[dict(path=p, count=c) for p, c in s["strings_paths"].most_common(25)],
                    absolute=[p for p in s["strings_paths"] if re.match(r"^[A-Za-z]:\\\\|^/(home|usr|Users|tmp)/", p)][:10],
                    backslashes=[p for p in s["strings_paths"] if "\\\\" in p][:10],
                    saves=[p for p, _ in s["strings_saves"].most_common(10)])
    network = H["net"].report()
    audio_apis = H["audio"].report()
    assets = asset_inventory(adir)
    genre = genre_guess(H["genre"])

    # ------------------------------------------------------------------ verdicts
    blockers, findings, stop = [], [], None
    if not proj["c_files"]:
        other = ", ".join(f"{k} ({v})" for k, v in proj["languages"].items()) or "no recognised source"
        stop = dict(reason="no-c-cpp", tell_the_user=f"No C/C++ source here ({other}). ps-vita-porter ports C/C++ games with their full "
                    "source. If you only have the game's binary, universal-decompiler (`ud`) can reconstruct its source first. If you "
                    "explicitly want an attempt anyway, it's best effort and gets logged in PORTLOG.md.")
    elif proj["engines"] and proj["c_files"] < 20:
        e = proj["engines"][0]
        stop = dict(reason="engine", tell_the_user=f"This is a {e['name']} project ({e['evidence']}): {e['why']}. ps-vita-porter refuses "
                    "it by default; if you explicitly insist, the agent may attempt a best-effort port and logs that you asked.")
    elif not proj["build_systems"]:
        stop = dict(reason="no-build", tell_the_user="No build system found (no CMakeLists.txt, Makefile, project files...). The project must "
                    "build on PC first. If the source is incomplete, use universal-decompiler to reconstruct it.")
    if proj.get("ud", {}).get("incomplete"):
        findings.append(f"ud repo: {proj['ud']['incomplete']} function(s) in decomp/progress.json are not ported yet: the PC build must be "
                        "complete and working before the Vita port (finish it with universal-decompiler)")
    if proj["c_files"] and not proj["cmake"] and proj["build_systems"]:
        findings.append(f"build system is {', '.join(proj['build_systems'])}, not CMake: add a CMake build first (PC target), then the Vita target")
    for d in deps:
        if d["status"] in ("blocker",):
            blockers.append(f"{d['name']}: {d['replacement']}")
        elif d["status"] in ("platform-layer", "replace", "build", "strip"):
            findings.append(f"{d['name']} ({d['status']}): {d.get('replacement') or ''}".rstrip(": "))
    if risky:
        findings.append("GL features vitaGL may not cover: " + ", ".join(x["name"] for x in risky) + " (references/vitagl.md)")
    if glsl:
        findings.append(f"GLSL shaders ({', '.join(glsl)}): runtime-compiled through vitaGL (GLSL translator / CG) with libshacccg.suprx; "
                        "test the shader path early")
    if portability["simd"]:
        findings.append(f"x86 SIMD in {portability['simd'][0]['where'][0]}...: NEON (arm_neon.h) or the scalar fallback")
    if portability["asm"]:
        findings.append(f"inline assembly ({portability['asm'][0]['where'][0]}...): rewrite in C or ARM")
    if portability["sixty_four_bit"]:
        findings.append(f"{sum(x['count'] for x in portability['sixty_four_bit'])} 64-bit assumption(s): the Vita is 32-bit ARMv7 (pointers and long are 4 bytes)")
    if portability["alignment"]:
        findings.append("packed structs / unaligned typed loads: ARMv7 faults on unaligned 64-bit/float/NEON access; use memcpy")
    if inp["text_input"]:
        findings.append("text input: the Vita needs the system IME dialog (SceImeDialog) for typing")
    if network:
        findings.append("network features: " + ", ".join(x["name"] for x in network) + " (strip or keep: intake)")
    if files_io["absolute"] or files_io["backslashes"]:
        findings.append("hard-coded absolute paths or backslashes: route every path through the platform layer (app0:, ux0:data/)")
    for a in audio_apis:
        if a["name"] in ("FMOD", "BASS", "XAudio2/DirectSound", "waveOut"):
            findings.append(f"audio through {a['name']}: replace behind the audio layer (SDL audio / SDL_mixer / OpenAL Soft)")
    if assets.get("found"):
        e = assets["estimate"]
        if e["textures_over_cdram"]:
            findings.append(f"decoded textures ~{human(e['texture_bytes'])} exceed CDRAM ({CDRAM_MB} MiB): downscale/compress/stream (intake)")
        if assets["textures"]["over_4096"]:
            blockers.append(f"{len(assets['textures']['over_4096'])} texture(s) over 4096 px, the GPU's limit: they must be downscaled")
    if api in ("Direct3D", "Vulkan"):
        blockers.append(f"the renderer uses {api}: it needs an OpenGL (vitaGL) backend in the platform layer before anything shows on the Vita")

    from vita_porter.intake import questions
    report = dict(project=proj, dependencies=deps, graphics=graphics, input=inp, display=display, portability=portability, threads=threads,
                  files=files_io, network=network, audio=dict(apis=audio_apis), assets=assets, genre=genre,
                  quit=s["quit"].report(), findings=findings, blockers=blockers, stop=stop, source_files=s["source_files"],
                  files_indexed=len(files), config=cfg)
    report["app"] = cfg.get("app", {})
    report["intake"] = questions(report, root)
    report.pop("config")
    report.pop("app")
    return report


def format_report(r: dict, questions_only: bool = False) -> str:
    L = []
    p = r["project"]
    if not questions_only:
        L.append(f"{p['root']}")
        L.append(f"  languages:  {', '.join(f'{k} ({v} files)' for k, v in p['languages'].items()) or 'none recognised'}")
        L.append(f"  build:      {', '.join(p['build_systems']) or 'none found'}")
        if p["ud_repo"]:
            u = p.get("ud", {})
            fn = u.get("functions")
            L.append("  ud repo:    universal-decompiler reconstruction" + (f"; functions {fn}" if fn else "")
                     + (f"; platform layer {u['platform_layer']} ({', '.join(u.get('platform_backends', [])[:6])})" if u.get("platform_layer") else ""))
        for e in p["engines"]:
            L.append(f"  ENGINE:     {e['name']} ({e['evidence']}): {e['why']}")
        L.append("  dependencies:")
        for d in r["dependencies"]:
            what = f"vdpm {d['vdpm']}" if d.get("vdpm") and d["status"] == "available" else d.get("replacement") or ""
            L.append(f"    [{d['status']:>14}] {d['name']}: {what}  ({d['evidence']})")
        if not r["dependencies"]:
            L.append("    (none recognised)")
        g = r["graphics"]
        L.append(f"  graphics:   {g['summary']}")
        if g["gl_features"]:
            L.append("              " + ", ".join(f"{x['name']} x{x['count']}" for x in g["gl_features"]))
        i = r["input"]
        apis = ", ".join(x["name"] for x in i["apis"]) or "none found"
        L.append(f"  input:      {apis}; {i['distinct_keys']} distinct keys" + ("; mouse" if i["mouse_used"] else "")
                 + (" (relative)" if i["relative_mouse"] else "") + ("; wheel" if i["wheel"] else "") + ("; gamepad" if i["gamepad"] else "")
                 + ("; TEXT INPUT" if i["text_input"] else ""))
        if i["keys"]:
            L.append("              keys: " + ", ".join(f"{k['key']}" for k in i["keys"][:24]))
        if i["actions_enum"]:
            L.append("              actions (enum): " + ", ".join(i["actions_enum"][:20]))
        d = r["display"]
        if d["resolutions"]:
            L.append("  display:    " + ", ".join(f"{x['width']}x{x['height']} ({x['where']})" for x in d["resolutions"][:4])
                     + f"; filtering: nearest x{r['graphics']['nearest_filter_uses']}, linear x{r['graphics']['linear_filter_uses']}")
        pt = r["portability"]
        L.append(f"  portability: 64-bit assumptions {sum(x['count'] for x in pt['sixty_four_bit'])}, SIMD {sum(x['count'] for x in pt['simd'])}, "
                 f"asm {sum(x['count'] for x in pt['asm'])}, alignment {sum(x['count'] for x in pt['alignment'])}")
        th = r["threads"]["apis"]
        L.append(f"  threads:    {', '.join(f'{x['name']} x{x['count']}' for x in th) or 'none found'}")
        f = r["files"]
        L.append(f"  file I/O:   {', '.join(x['name'] for x in f['apis']) or 'none found'}" + (f"; saves: {', '.join(f['saves'][:4])}" if f["saves"] else ""))
        if r["network"]:
            L.append(f"  network:    {', '.join(x['name'] for x in r['network'])}")
        if r["audio"]["apis"]:
            L.append(f"  audio:      {', '.join(x['name'] for x in r['audio']['apis'])}")
        a = r["assets"]
        if a.get("found"):
            t = a["textures"]
            L.append(f"  assets:     {a['dir']}: {a['files']} files, {human(a['total_bytes'])}; {t['count']} textures (max side {t['max_side']}, "
                     f"median {t['median_side']}), {a['audio']['count']} audio, {len(a['videos'])} videos")
            e = a["estimate"]
            L.append(f"              estimate: textures ~{human(e['texture_bytes'])} decoded (CDRAM budget {CDRAM_MB} MiB), other data "
                     f"~{human(e['other_ram_bytes'])} (newlib heap {HEAP_MB} MiB by default, MAIN {MAIN_MB} MiB)")
        else:
            L.append("  assets:     no asset folder found (pass --assets <dir>)")
        L.append(f"  genre:      {r['genre']['guess']} {r['genre']['scores']}")
        for x in r["findings"]:
            L.append(f"  FINDING:    {x}")
        for x in r["blockers"]:
            L.append(f"  BLOCKER:    {x}")
        if r["stop"]:
            L.append(f"  STOP:       {r['stop']['tell_the_user']}")
        L.append("")
    L.append("Intake questions (ask once, grouped; every answer + declined alternatives + reason go in PORT_PLAN.md):")
    topic = None
    for q in r["intake"]:
        if q["topic"] != topic:
            topic = q["topic"]
            L.append(f"\n  [{topic}]")
        L.append(f"  - {q['question']}")
        L.append(f"      recommended: {q['recommended']}")
        L.append(f"      why: {q['why']}")
        if q.get("options"):
            L.append(f"      options: {' | '.join(q['options'])}")
    return "\n".join(L)


def main(a):
    r = scan(a.path, a.assets)
    if a.json:
        emit_json(r if not a.questions else r["intake"])
    else:
        print(format_report(r, a.questions))
    return PROBLEM if r["stop"] else OK


def register(sub):
    import argparse
    p = sub.add_parser("scan", help="analyse the source project: deps vs vdpm, graphics, input, resolutions, portability, assets; intake questions",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("path", nargs="?", help="the source tree (default: the current repo)")
    p.add_argument("--assets", help="the asset folder (default: vita.toml [assets] source, else data/, assets/, ...)")
    p.add_argument("--questions", action="store_true", help="only the intake questions")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=main)
