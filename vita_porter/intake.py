"""The intake questions `vita scan` emits, each with a recommended answer grounded in the scan: the game's genre,
its original control scheme, its UI and the asset analysis. The vita-recon skill documents the same logic.

Rules that hold for every recommendation:
- every optional feature (front touch, rear touch, gyro) has an "off" choice;
- nothing that clashes with the spirit of the game (gyro aiming fits a shooter, never a menu-driven RPG);
- rear-touch shortcuts never fire on a light grip: off by default, and when used, only on deliberate gestures
  (a held press in a zone, never a plain touch);
- not asked (defaults): the confirm button follows the system setting; glyphs are original or CC0, never Sony's;
  saves go in ux0:data/<name>/.
"""
from __future__ import annotations

import re
from pathlib import Path

VITA_W, VITA_H = 960, 544
# Vita inputs available to games: 4 face buttons, L, R, Start, Select, D-pad (4), 2 sticks. No L2/R2/L3/R3.
FACE = ["Cross", "Circle", "Square", "Triangle"]

# original key (SDL scancode / keycode / GLFW / VK names, upper-cased) -> (action guess, Vita suggestion)
KEY_MAP = [
    (r"^(W|A|S|D|UP|DOWN|LEFT|RIGHT|KP_[2468])$", "move", "left stick + D-pad"),
    (r"^(SPACE)$", "jump / main action", "Cross"),
    (r"^(RETURN|ENTER|KP_ENTER)$", "confirm", "confirm button (system setting: Cross or Circle)"),
    (r"^(ESCAPE|ESC)$", "pause / back", "Start (pause), Circle/back in menus"),
    (r"^(BACKSPACE)$", "back", "the cancel button (the other of Cross/Circle)"),
    (r"^(LSHIFT|RSHIFT|SHIFT|LEFTSHIFT)$", "run / modifier", "L"),
    (r"^(LCTRL|RCTRL|CONTROL|LCONTROL|CTRL)$", "crouch / secondary", "R or Circle"),
    (r"^(LALT|RALT|MENU)$", "modifier", "L+R combo or remove"),
    (r"^(TAB)$", "map / inventory / menu", "Select"),
    (r"^(E|F)$", "interact / use", "Square"),
    (r"^(Q)$", "ability / previous", "Triangle or L"),
    (r"^(R)$", "reload / restart", "Triangle"),
    (r"^(Z|X|C|V|J|K)$", "action button", "a face button (Cross/Square/Circle/Triangle)"),
    (r"^([0-9]|KP_[0-9])$", "select slot / weapon", "D-pad left/right cycling, or a front-touch hotbar"),
    (r"^(F[0-9]{1,2})$", "debug / quick save / options", "options menu entries (not mapped to buttons)"),
    (r"^(P|PAUSE)$", "pause", "Start"),
    (r"^(M)$", "map", "Select"),
    (r"^(I)$", "inventory", "Triangle or Select"),
]
DEBUG_KEYS = re.compile(r"^(F[0-9]{1,2}|GRAVE|BACKQUOTE|PRINTSCREEN|SCROLLLOCK|INSERT|HOME|END|PAGEUP|PAGEDOWN|DELETE|NUMLOCKCLEAR)$")


def suggest_title_id(name: str) -> str:
    from vita_porter.init import suggest_title_id as s
    return s(name)


def map_keys(keys: list[dict]) -> tuple[list[dict], list[str]]:
    rows, unmapped = [], []
    seen = set()
    for k in keys:
        key = k["key"]
        if key in seen:
            continue
        seen.add(key)
        for rx, action, vita in KEY_MAP:
            if re.match(rx, key):
                rows.append(dict(key=key, action=action, vita=vita))
                break
        else:
            unmapped.append(key)
    return rows, unmapped


def gcd_scale(w: int, h: int) -> tuple[int, int, str]:
    """Best fit of w x h inside 960x544 keeping the aspect ratio: (out_w, out_h, kind)."""
    s = min(VITA_W / w, VITA_H / h)
    return round(w * s), round(h * s), ("pillarbox" if round(w * s) < VITA_W else "letterbox" if round(h * s) < VITA_H else "exact")


def questions(r: dict, root: Path) -> list[dict]:
    Q: list[dict] = []
    genre = r["genre"]["guess"]
    inp = r["input"]
    keys = [k for k in inp["keys"] if not DEBUG_KEYS.match(k["key"])]
    rows, unmapped = map_keys(keys)
    actions = inp["actions_enum"]
    n_actions = len(actions) if actions else len({row["action"] for row in rows}) + len(unmapped)
    mouse = inp["mouse_used"]
    rel_mouse = inp["relative_mouse"]
    tex = r["assets"].get("textures", {}) if r["assets"].get("found") else {}
    pixel_art = bool(tex) and tex.get("median_side", 999) <= 256 and r["graphics"]["nearest_filter_uses"] >= r["graphics"]["linear_filter_uses"]
    if not tex and r["graphics"]["nearest_filter_uses"] > r["graphics"]["linear_filter_uses"]:
        pixel_art = True
    orig = r["display"]["original"]
    ud = r["project"]["ud_repo"]

    def ask(topic, qid, question, recommended, why, options=None):
        Q.append(dict(topic=topic, id=qid, question=question, recommended=recommended, why=why, options=options or []))

    # ------------------------------------------------------------------ controls
    if actions:
        mapping = "; ".join(f"{a} -> {v}" for a, v in zip(actions, _assign(actions), strict=False))
        why = f"the game's own action list ({len(actions)} actions in its input enum)"
    elif rows:
        mapping = "; ".join(f"{row['key']} ({row['action']}) -> {row['vita']}" for row in rows[:14])
        why = "keys the code reads, by their usual role"
    else:
        mapping = "list every action from the game's input code, then assign face buttons by frequency of use"
        why = "no key handling recognised in the source"
    ask("Controls", "mapping", "How should every original action map to the Vita's buttons and sticks (two sticks, D-pad, "
        "L/R only: there is no L2/R2/L3/R3)?", mapping, why + ("; unmapped keys: " + ", ".join(unmapped[:10]) if unmapped else ""))
    if n_actions == 0:
        rec = "decide once the action list is known (read the input code); by default L/R + button combos before touch"
        why = "no actions recognised in the source"
    elif n_actions > 12:
        rec = ("recover the extra actions with L/R + button combos for rare actions and a front-touch overlay (virtual buttons) for "
               "menu-like ones; rear-touch zones only if the user wants them")
        why = f"{n_actions} actions for 12 physical inputs"
    else:
        rec = "not needed: everything fits on physical buttons (L2/R2/L3/R3-style actions go to L/R or a face button)"
        why = f"{n_actions} actions fit the Vita's 12 physical inputs"
    ask("Controls", "extra-actions", "How are actions that don't fit (or would have used L2/R2/L3/R3) recovered?", rec, why,
        ["L/R + button combos", "front-touch virtual buttons", "rear-touch zones (deliberate hold only)", "drop rarely used actions to a menu"])
    if mouse and genre in ("strategy", "adventure", "puzzle") or (mouse and not keys):
        ask("Controls", "front-touch", "How should the front touchscreen be used?",
            "direct interaction: tap = click at that point (the game is mouse-driven), plus a right stick-driven cursor for precise use",
            f"the original is mouse-driven ({'genre ' + genre if genre not in ('unknown', 'unclear') else 'mouse handling found'})",
            ["direct interaction", "menus only", "virtual buttons", "off"])
    elif mouse:
        ask("Controls", "front-touch", "How should the front touchscreen be used?",
            "menus only: tap menu items and buttons; gameplay stays on physical controls",
            "the original uses the mouse for menus/UI as well as keys for play", ["menus only", "direct interaction", "virtual buttons", "off"])
    else:
        ask("Controls", "front-touch", "How should the front touchscreen be used?", "off (or menus only if the user likes touch)",
            "the original has no mouse or pointer interaction", ["off", "menus only", "virtual buttons"])
    ask("Controls", "rear-touch", "Should the rear touchpad do anything?",
        "off" if n_actions <= 12 else "two zones (left/right halves) as extra shoulder buttons, triggered only by a deliberate hold, with an option to disable",
        "the rear pad is under the fingers while gripping: accidental triggers are the main risk"
        + ("" if n_actions <= 12 else f"; {n_actions} actions need extra inputs"),
        ["off", "zones as extra shoulder buttons (hold to trigger)", "zones mapped to rarely used actions"])
    if genre == "shooter" and (rel_mouse or mouse):
        ask("Controls", "gyro", "Use the gyro for fine aiming?", "optional gyro aiming on top of the right stick, off by default, with a sensitivity setting",
            "a shooter with mouse aiming: gyro fine-tuning is the closest thing to a mouse", ["off", "aim assist (on top of the stick)", "aim only while L is held"])
    else:
        ask("Controls", "gyro", "Use the gyro?", "off",
            f"nothing in the game calls for motion control (genre {genre}); gyro would clash with the original design",
            ["off"] + (["camera nudging"] if genre in ("racing",) else []))
    moves = any(row["action"] == "move" for row in rows)
    if rel_mouse:
        cam = "right stick for the camera/look (with sensitivity and invert-Y options), left stick to move"
        why = "the original uses mouse look (relative mouse)"
    elif mouse and not moves:
        cam = "right stick drives an on-screen cursor (front touch taps where precision isn't needed); D-pad navigation for menus"
        why = "the original is pointer-driven with no movement keys"
    elif mouse:
        cam = "left stick + D-pad move the character and navigate menus; the mouse's menu clicks become front-touch taps"
        why = "movement is on keys; the mouse only clicks UI"
    else:
        cam = "left stick + D-pad for movement and menus"
        why = "keyboard-only original"
    ask("Controls", "character-camera-cursor", "How are the character, the camera and any cursor controlled?", cam, why)

    # ------------------------------------------------------------------ UI
    ask("In-game UI", "glyphs", "Replace keyboard/mouse prompts with Vita button glyphs?",
        "yes: original glyph drawings (or CC0) for Cross/Circle/Square/Triangle/L/R/Start/Select, following the confirm-button setting",
        "prompts must match the buttons; Sony's glyph art can't be used")
    ask("In-game UI", "remap", "Where does the key-remapping menu live?",
        "in the game's own options menu if it has one, else a small overlay opened with Start+Select", "players expect remapping in options",
        ["game options menu", "dedicated overlay (Start+Select)", "no remapping"])
    ask("In-game UI", "touch-hints", "How are touch zones shown or hinted?",
        "subtle outlines for virtual buttons only while they're usable; nothing drawn for rear zones (described in the options/help)"
        if n_actions > 12 or mouse else "nothing to show (touch is off or limited to tapping visible menu items)",
        "keep the original UI clean; hints only where a touch zone isn't a visible element")

    # ------------------------------------------------------------------ resolution / scaling
    if orig:
        w, h = orig["width"], orig["height"]
        ow, oh, kind = gcd_scale(w, h)
        if pixel_art:
            k = min(VITA_W // w, VITA_H // h)
            if k >= 1 and k * h >= 0.9 * VITA_H:
                rec = f"render at {w}x{h} and scale x{k} with nearest filtering ({k * w}x{k * h}, centred)"
            else:
                rec = f"render at {w}x{h}, scale to fit the height ({ow}x{oh}, {kind}) with nearest filtering (or sharp-bilinear)"
        elif w * h <= VITA_W * VITA_H:
            rec = f"render at {w}x{h} internally and scale to {ow}x{oh} ({kind}), linear filtering"
        else:
            rec = f"render at 960x544 (or {ow}x{oh} keeping {w}:{h}) instead of {w}x{h}; drop to 720x408 internal if profiling shows the GPU is the limit"
        why = f"original {w}x{h} ({orig['where']}), {'pixel art' if pixel_art else 'not pixel art'}"
    else:
        rec = "native 960x544 if the game is resolution-independent, otherwise its own resolution scaled to fit"
        why = "no hard-coded resolution found"
    ask("Resolution and scaling", "internal-resolution", "Native 960x544, or a lower internal resolution upscaled for performance?", rec, why,
        ["native 960x544", "lower internal resolution, upscaled", "original resolution, scaled"])
    if orig and abs(orig["width"] / orig["height"] - VITA_W / VITA_H) > 0.02:
        ask("Resolution and scaling", "aspect", f"The game is {orig['width']}:{orig['height']} ({orig['width'] / orig['height']:.2f}:1) and the Vita "
            "is 960:544 (1.76:1). Letterbox/pillarbox, stretch or crop?", "pillarbox/letterbox (keep the aspect ratio), black or a subtle border",
            "stretching distorts the art; cropping can hide UI", ["letterbox/pillarbox", "stretch", "crop"])
    ask("Resolution and scaling", "ui-scale", "UI and text scale for a 5-inch screen?",
        "scale UI and text so the smallest text is at least ~16 px tall on the 544-line screen; enlarge if the original's is smaller after scaling",
        "PC UIs are designed for monitors at arm's length")
    ask("Resolution and scaling", "filtering", "Filtering when scaling?", "nearest (sharp)" if pixel_art else "linear",
        "pixel art detected (small textures, GL_NEAREST/nearest hints)" if pixel_art else "the art isn't pixel art")

    # ------------------------------------------------------------------ textures / memory
    a = r["assets"]
    if a.get("found"):
        e = a["estimate"]
        tb = e["texture_bytes"]
        mib = tb / (1 << 20)
        big = len(tex.get("over_2048", [])) + len(tex.get("over_4096", []))
        if pixel_art:
            rec = "no downscaling, no compression (pixel art and UI stay lossless)"
        elif mib > 90 or big:
            rec = "downscale textures over 1024 px by half; keep UI/text at full size"
        else:
            rec = "no downscaling needed"
        ask("Textures and memory", "downscale", "Texture downscaling policy?", rec,
            f"decoded textures ~{mib:.0f} MiB vs 112 MiB CDRAM; {big} texture(s) over 2048 px; median side {tex.get('median_side', 0)} px")
        comp = ("none (PNG/TGA, nearest)" if pixel_art else "DXT1 (opaque) / DXT5 (alpha) for world textures, uncompressed for UI and text"
                if mib > 60 else "none needed; DXT1/DXT5 if profiling shows memory pressure")
        ask("Textures and memory", "compression", "Texture compression format?", comp,
            "the Vita samples DXT (UBC), PVRTC and ETC1 natively; DXT encodes with `vita assets convert`; lossy formats hurt pixel art and text",
            ["DXT1/DXT5 (UBC)", "PVRTC", "ETC1", "none"])
        total = tb + e["other_ram_bytes"]
        ask("Textures and memory", "streaming", "Stream assets or preload them?",
            "preload (it fits)" if total < (100 << 20) else "stream levels/music and keep only the current level's textures resident",
            f"estimated resident data ~{total / (1 << 20):.0f} MiB vs a 128 MiB default heap and 112 MiB CDRAM")
    else:
        ask("Textures and memory", "assets-unknown", "Where are the game's assets? (vita scan found no asset folder)",
            "point vita scan at them (vita scan --assets <dir>) before deciding downscaling, compression and streaming",
            "the memory decisions depend on the asset analysis")

    # ------------------------------------------------------------------ assets mode
    ask("Assets", "mode", "Embed the assets in the .vpk, or keep them external in ux0:data/<name>/?",
        "external" if ud or (a.get("found") and a.get("total_bytes", 0) > (500 << 20)) else "embedded",
        ("a universal-decompiler repo: the assets come from the user's own copy, so a .vpk without them can be shared and the user "
         "copies their data separately") if ud else
        ("large data set: a smaller .vpk installs faster" if a.get("found") and a.get("total_bytes", 0) > (500 << 20) else
         "the assets are the project's own and small: one self-contained .vpk"), ["embedded", "external"])

    # ------------------------------------------------------------------ frame rate
    heavy = r["graphics"]["api"] in ("OpenGL", "Direct3D", "Vulkan") and (r["graphics"]["glsl_versions"] or (tex and tex.get("count", 0) > 300))
    ask("Frame rate", "fps", "Target frame rate?", "30 fps (locked), 60 if profiling allows" if heavy else "60 fps",
        "shader-heavy 3D on a 444 MHz Cortex-A9 + SGX543MP4+" if heavy else "light 2D/fixed-function rendering", ["30", "60"])

    # ------------------------------------------------------------------ identity
    app = r.get("app", {})
    name = app.get("name") or Path(r["project"]["root"]).name
    tid = app.get("title_id") or suggest_title_id(name)
    from vita_porter.common import title_id_problems
    probs = title_id_problems(tid)
    ask("App identity", "title-id", "Title ID (4 uppercase letters + 5 digits)?", tid,
        ("from vita.toml" if app.get("title_id") else "derived from the name") + "; not a reserved prefix (PCS*, NP**, VSDK...)"
        + (f"; PROBLEM: {probs[0]}" if probs else "") + "; check it against VitaDB/known IDs before release")
    ask("App identity", "name", "Display name under the bubble?", name, ("from vita.toml" if app.get("name") else "the project's name")
        + "; short names fit the bubble")
    ask("App identity", "version", "Version?", app.get("version") or "01.00", "param.sfo APP_VER format ##.##")

    # ------------------------------------------------------------------ flagged by the scan
    aud = r["audio"]["apis"]
    afmt = a.get("audio", {}).get("formats", {}) if a.get("found") else {}
    if aud or afmt:
        exotic = [x["name"] for x in aud if x["name"] in ("FMOD", "BASS", "XAudio2/DirectSound", "waveOut")]
        ask("Flagged by vita scan", "audio", "Audio: how are sound and music played and stored?",
            ("replace " + ", ".join(exotic) + " with SDL audio/SDL_mixer; " if exotic else "keep the audio code on SDL; ")
            + ("music as OGG (streamed), effects as WAV 22050 Hz mono" if afmt else "formats as they are"),
            f"audio APIs: {', '.join(x['name'] for x in aud) or 'unknown'}; formats: {afmt or 'unknown'}")
    if r["files"]["saves"] or r["files"]["hints"]:
        ask("Flagged by vita scan", "saves", "Saves and settings?", "ux0:data/<data_folder>/ (default), same file format as the PC version",
            f"save-like paths in the code: {', '.join(r['files']['saves'][:4]) or 'see file I/O hints'}")
    if r["quit"]:
        ask("Flagged by vita scan", "quit", "How does the player quit?",
            "hide the 'Quit/Exit' menu entry (Vita apps are closed from LiveArea), or keep it and exit cleanly with sceKernelExitProcess",
            "the original has a quit path; on the Vita the PS button + closing the app is the norm",
            ["hide Quit", "keep Quit (clean exit)"])
    if r["network"]:
        ask("Flagged by vita scan", "online", "Online features: " + ", ".join(x["name"] for x in r["network"]) + ". Strip or keep?",
            "strip platform services (Steam, Discord) and online play; keep plain HTTP only if the game can't work without it",
            "PC services have no Vita equivalent; Wi-Fi play needs extra testing", ["strip", "keep (Wi-Fi)"])
    if inp["text_input"]:
        ask("Flagged by vita scan", "text-input", "The game takes typed text: use the system keyboard (IME dialog)?",
            "yes: open SceImeDialog where the game asks for text", "the Vita has no keyboard")
    if a.get("found") and a.get("videos"):
        ask("Flagged by vita scan", "videos", f"{len(a['videos'])} video file(s): play, re-encode or skip?",
            "re-encode locally to H.264 for SceAvPlayer (from the user's own copy) or skip intro videos", "PC codecs (Bink...) have no Vita decoder")
    langs = [p for p in r["files"]["paths"] if re.search(r"(lang|locale|i18n|\.po$|strings_\w+)", p["path"], re.I)]
    if langs:
        ask("Flagged by vita scan", "language", "Language selection?", "follow the system language (SCE_SYSTEM_PARAM_ID_LANG) when the game has it, else the game's setting",
            "localisation files found: " + ", ".join(p["path"] for p in langs[:3]))
    for i, q in enumerate(Q):
        q["n"] = i + 1
    return Q


def _assign(actions: list[str]) -> list[str]:
    """Physical inputs for an ordered action list (movement first, then the most important actions on face buttons)."""
    out = []
    face = ["Cross", "Square", "Circle", "Triangle", "R", "L", "Select", "Start"]
    for a in actions:
        low = a.lower()
        if low in ("up", "down", "left", "right") or "move" in low:
            out.append(f"left stick / D-pad {low}" if low in ("up", "down", "left", "right") else "left stick")
        elif any(w in low for w in ("confirm", "accept", "ok", "select")):
            out.append("confirm button (system setting)")
        elif any(w in low for w in ("cancel", "back")):
            out.append("cancel button (system setting)")
        elif any(w in low for w in ("pause", "menu", "start")):
            out.append("Start")
        elif face:
            out.append(face.pop(0))
        else:
            out.append("touch/combo")
    return out


