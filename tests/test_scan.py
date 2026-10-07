"""vita scan on synthetic fixture projects (written in-test): CMake + GL, a Direct3D blocker, SSE, a hard-coded
640x480, a fake universal-decompiler repo, refusals, and the false positives found on the example."""
from __future__ import annotations

import json

from conftest import make, vita

from vita_porter.images import write_png
from vita_porter.scan import scan

CMAKE_GL = """cmake_minimum_required(VERSION 3.20)
project(demo CXX)
find_package(SDL2 REQUIRED)
find_package(OpenGL REQUIRED)
add_executable(demo src/main.cpp)
"""
MAIN_GL = r"""
#include <SDL2/SDL.h>
#include <GL/gl.h>
#include <SDL2/SDL_mixer.h>
int main() {
    SDL_Window* w = SDL_CreateWindow("demo", 0, 0, 1280, 720, SDL_WINDOW_OPENGL);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 2);
    const Uint8* k = SDL_GetKeyboardState(nullptr);
    if (k[SDL_SCANCODE_W] || k[SDL_SCANCODE_A] || k[SDL_SCANCODE_S] || k[SDL_SCANCODE_D]) {}
    if (k[SDL_SCANCODE_SPACE]) jump();
    if (k[SDL_SCANCODE_ESCAPE]) pause();
    SDL_Event e; if (e.type == SDL_MOUSEBUTTONDOWN && e.button.button == SDL_BUTTON_LEFT) click();
    glBegin(GL_QUADS); glEnd();
    GLuint fb; glGenFramebuffers(1, &fb);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    FILE* f = fopen("data/levels/level1.map", "rb");
    FILE* s = fopen("save/slot1.sav", "wb");
    Mix_PlayChannel(-1, 0, 0);
    if (e.type == SDL_QUIT) return 0;
}
"""


def gl_project(root):
    make(root, {"CMakeLists.txt": CMAKE_GL, "src/main.cpp": MAIN_GL})
    (root / "assets").mkdir()
    write_png(root / "assets" / "tiles.png", 512, 512, b"\x10\x20\x30" * 512 * 512)
    write_png(root / "assets" / "ui.png", 2560, 64, b"\x10\x20\x30" * 2560 * 64)
    make(root, {"assets/music.ogg": b"OggS" + b"\0" * 4000, "assets/jump.wav": b"RIFF" + b"\0" * 2000})
    return root


def q(r, qid):
    return next(x for x in r["intake"] if x["id"] == qid)


def test_cmake_gl_project(tmp_path):
    r = scan(gl_project(tmp_path / "p"))
    assert r["stop"] is None
    assert r["project"]["cmake"] and not r["project"]["ud_repo"]
    deps = {d["id"]: d for d in r["dependencies"]}
    assert deps["sdl2"]["status"] == "available" and deps["sdl2"]["vdpm"] == "sdl2"
    assert deps["opengl"]["vdpm"] == "vitaGL" and deps["sdl2_mixer"]["vdpm"] == "sdl2_mixer"
    g = r["graphics"]
    assert g["api"] == "OpenGL" and g["gl_context_major"] == "2"
    feats = {x["name"] for x in g["gl_features"]}
    assert "immediate mode (glBegin/glEnd)" in feats and "framebuffer objects" in feats
    keys = {k["key"] for k in r["input"]["keys"]}
    assert {"W", "A", "S", "D", "SPACE", "ESCAPE"} <= keys
    assert r["input"]["mouse_used"] and not r["input"]["relative_mouse"]
    assert r["display"]["original"]["width"] == 1280 and r["display"]["original"]["height"] == 720
    assert any("save/slot1.sav" in s for s in r["files"]["saves"])
    a = r["assets"]
    assert a["found"] and a["textures"]["count"] == 2 and a["textures"]["max_side"] == 2560
    assert a["textures"]["over_2048"] and a["estimate"]["texture_bytes"] == 512 * 512 * 4 + 2560 * 64 * 4
    # every topic of the intake is there, each with a recommendation and a reason
    topics = {x["topic"] for x in r["intake"]}
    assert {"Controls", "In-game UI", "Resolution and scaling", "Textures and memory", "Assets", "Frame rate", "App identity",
            "Flagged by vita scan"} <= topics
    for x in r["intake"]:
        assert x["recommended"] and x["why"], x
    for opt in ("front-touch", "rear-touch", "gyro"):
        assert any(o.startswith("off") for o in q(r, opt)["options"]), f"{opt} must offer off"
    assert q(r, "front-touch")["recommended"].startswith("menus only")
    assert q(r, "rear-touch")["recommended"] == "off"
    assert q(r, "gyro")["recommended"] == "off"
    assert "SPACE" in q(r, "mapping")["recommended"] and "Cross" in q(r, "mapping")["recommended"]
    assert q(r, "mode")["recommended"] == "embedded"
    assert q(r, "quit") and q(r, "saves") and q(r, "audio")
    assert "Over 1024" in q(r, "downscale")["recommended"].title() or "downscale" in q(r, "downscale")["recommended"]


def test_d3d_is_a_blocker(tmp_path):
    root = make(tmp_path / "d3d", {"CMakeLists.txt": "project(x)\nadd_executable(x main.cpp)\n",
                                   "main.cpp": "#include <windows.h>\n#include <d3d9.h>\nIDirect3DDevice9* dev;\n"
                                               "int f(){ Direct3DCreate9(32); return GetAsyncKeyState(VK_SPACE); }\n"})
    r = scan(root)
    assert r["graphics"]["api"] == "Direct3D"
    assert any("Direct3D" in b for b in r["blockers"])
    st = {d["id"]: d["status"] for d in r["dependencies"]}
    assert st["d3d"] == "blocker" and st["win32"] == "platform-layer"
    assert r["stop"] is None, "a blocker is reported, not a refusal"
    assert {"SPACE"} <= {k["key"] for k in r["input"]["keys"]}


def test_sse_and_64bit(tmp_path):
    root = make(tmp_path / "sse", {"CMakeLists.txt": "project(x)\n", "m.cpp": "#include <xmmintrin.h>\n"
                "__m128 add(__m128 a, __m128 b){ return _mm_add_ps(a, b); }\n"
                "static_assert(sizeof(void*) == 8, \"64-bit only\");\n"
                "long h(void* p){ return reinterpret_cast<long>(p); }\n"
                "#pragma pack(push, 1)\nstruct S { char c; int i; };\n"})
    r = scan(root)
    p = r["portability"]
    assert p["simd"] and p["sixty_four_bit"] and p["alignment"]
    assert any("SIMD" in f for f in r["findings"]) and any("64-bit" in f for f in r["findings"])


def test_hard_coded_640x480_pixel_art(tmp_path):
    root = make(tmp_path / "px", {"CMakeLists.txt": "project(x)\n",
                                  "g.c": "#define SCREEN_WIDTH 640\n#define SCREEN_HEIGHT 480\n"
                                         "void s(){ SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, \"nearest\"); glTexParameteri(0, 0, GL_NEAREST); }\n"})
    (root / "data").mkdir()
    for i in range(3):
        write_png(root / "data" / f"s{i}.png", 32, 32, b"\x01\x02\x03" * 32 * 32)
    r = scan(root)
    o = r["display"]["original"]
    assert (o["width"], o["height"]) == (640, 480)
    assert q(r, "aspect")["recommended"].startswith("pillarbox")
    assert "nearest" in q(r, "filtering")["recommended"]
    assert "fit the height" in q(r, "internal-resolution")["recommended"]   # x1 would fill only 88% of 544 lines
    assert q(r, "compression")["recommended"].startswith("none")


def test_fake_ud_repo(tmp_path):
    root = make(tmp_path / "ud", {
        "ud.toml": "[project]\nname = \"foo\"\nroute = \"native\"\n",
        "DECOMP_PLAN.md": "# Decompilation plan\n## Done criterion\n- [x] builds on Linux\n- [ ] reaches the main menu\n",
        "DECOMPLOG.md": "# DECOMPLOG\n",
        "decomp/progress.json": json.dumps({"version": 1, "functions": [{"address": "0x1", "status": "verified"},
                                                                        {"address": "0x2", "status": "ported"},
                                                                        {"address": "0x3", "status": "todo"}]}),
        "CMakeLists.txt": "project(foo)\nfind_package(SDL3 CONFIG)\n",
        "src/platform/platform.h": "#pragma once\nnamespace platform {\nenum class Key { Up, Down, Left, Right, Confirm, Cancel, Count };\n}\n",
        "src/platform/platform_sdl3.cpp": "#include <SDL3/SDL.h>\n",
        "src/main.cpp": "#include \"platform/platform.h\"\nint main(){}\n",
        "data/game.exe": b"MZ" + b"\0" * 100,
    })
    r = scan(root)
    u = r["project"]["ud"]
    assert r["project"]["ud_repo"] and u["platform_layer"] == "src/platform" and "platform_sdl3.cpp" in u["platform_backends"]
    assert u["functions"]["total"] == 3 and u["incomplete"] == 1
    assert [d["done"] for d in u["done_criterion"]] == [True, False]
    assert r["input"]["actions_enum"] == ["Up", "Down", "Left", "Right", "Confirm", "Cancel"]
    assert any("not ported yet" in f for f in r["findings"])
    assert q(r, "mode")["recommended"] == "external"
    assert "Confirm -> confirm button" in q(r, "mapping")["recommended"]
    assert any(d["id"] == "sdl3" for d in r["dependencies"])


def test_unity_project_is_refused(tmp_path):
    root = make(tmp_path / "u", {"ProjectSettings/ProjectVersion.txt": "m_EditorVersion: 2022.3.1f1\n",
                                 "Assets/Scripts/Player.cs": "class Player {}\n", "Assets/Main.unity": "%YAML\n"})
    r = vita("scan", str(root))
    assert r.returncode == 1 and "STOP" in r.stdout
    j = json.loads(vita("scan", str(root), "--json").stdout)
    assert j["stop"]["reason"] in ("no-c-cpp", "engine")


def test_no_build_system_and_python_project(tmp_path):
    root = make(tmp_path / "py", {"game.py": "print('hi')\n"})
    r = scan(root)
    assert r["stop"]["reason"] == "no-c-cpp" and "universal-decompiler" in r["stop"]["tell_the_user"]
    root2 = make(tmp_path / "nob", {"main.c": "int main(){return 0;}\n"})
    assert scan(root2)["stop"]["reason"] == "no-build"


def test_makefile_project_gets_a_cmake_finding(tmp_path):
    root = make(tmp_path / "mk", {"Makefile": "all:\n\tcc main.c\n", "main.c": "int main(){return 0;}\n"})
    r = scan(root)
    assert r["stop"] is None and any("add a CMake build first" in f for f in r["findings"])


def test_regressions_from_the_example(tmp_path):
    root = make(tmp_path / "reg", {
        "CMakeLists.txt": "project(x)\n",
        "src/gl.h": "#if defined(_WIN32)\n#include <windows.h>\n#endif\n",          # windows.h is not SIMD
        "src/platform/platform.h": "namespace platform { void present(); }\n",     # 'platform' is not a platformer
        "src/a.cpp": "void f(){ platform::present(); platform::present(); platform::present(); platform::present(); platform::present(); }\n",
        "build-vita-ext/CMakeCache.txt": "x\n", "build-vita-ext/CMakeFiles/a.d": "dep\n",   # a build tree: skipped
        "platform/vita/vitaport/vitaport.h": "#pragma once\n", "platform/vita/vitaport/vitaport_sim.c": "#include <SDL3/SDL.h>\nint k = SDL_SCANCODE_Q;\n",
    })
    r = scan(root)
    assert not r["portability"]["simd"]
    assert r["genre"]["guess"] != "platformer"
    assert "D" not in r["project"]["languages"]
    assert not any(d["id"] == "sdl3" for d in r["dependencies"]), "the vitaport kit is not the game"
    assert "Q" not in {k["key"] for k in r["input"]["keys"]}


def test_questions_flag_and_json(tmp_path):
    root = gl_project(tmp_path / "p")
    r = vita("scan", str(root), "--questions")
    assert r.returncode == 0 and "Intake questions" in r.stdout and "recommended:" in r.stdout and "dependencies:" not in r.stdout
    j = json.loads(vita("scan", str(root), "--questions", "--json").stdout)
    assert isinstance(j, list) and all({"topic", "question", "recommended", "why"} <= set(x) for x in j)
