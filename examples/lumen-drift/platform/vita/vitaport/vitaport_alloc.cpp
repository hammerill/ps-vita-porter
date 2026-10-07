// vitaport, memory cap for the PC "Vita simulation" profile. Shipped by ps-vita-porter (MIT).
//
// Counts what the game allocates and fails the way the Vita would when the budget is exceeded:
//   - GCC/Clang with GNU ld (Linux, MinGW): malloc/calloc/realloc/free are wrapped (-Wl,--wrap=...; VitaPort.cmake adds
//     the flags and VP_WRAP_MALLOC) for every object linked into the game. Shared libraries (SDL, GL drivers) aren't
//     counted: their Vita counterparts live in other pools anyway.
//   - everywhere else (MSVC, Apple ld64): C++ new/delete only.
// Budget: VITASIM_MEM_MB (default 128 = the Vita's default newlib heap; a port that sets _newlib_heap_size_user
// passes the same number). Over budget: VITASIM_OOM=abort (default: log and abort, so `vita sim` reports it) or
// null (return NULL like newlib's malloc on the Vita, for games that handle it).
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <new>

#if defined(_WIN32)
#include <malloc.h>
#define VP_USABLE(p) _msize(p)
#elif defined(__APPLE__)
#include <malloc/malloc.h>
#define VP_USABLE(p) malloc_size(p)
#else
#include <malloc.h>
#define VP_USABLE(p) malloc_usable_size(p)
#endif

namespace {
std::atomic<size_t> g_used{0}, g_peak{0};
std::atomic<int> g_oom{0};
size_t g_budget = 0;

size_t budget() {
    if (!g_budget) {
        const char* e = std::getenv("VITASIM_MEM_MB");
        long mb = e && *e ? std::atol(e) : 0;
        g_budget = (size_t)(mb > 0 ? mb : 128) << 20;
    }
    return g_budget;
}

bool admit(size_t size) {
    if (g_used.load(std::memory_order_relaxed) + size <= budget()) return true;
    g_oom.store(1);
    std::fprintf(stderr, "VITASIM OOM: allocation of %zu bytes with %zu in use exceeds the %zu MiB Vita budget\n", size,
                 g_used.load(), budget() >> 20);
    const char* mode = std::getenv("VITASIM_OOM");
    if (!mode || std::strcmp(mode, "null") != 0) std::abort();
    return false;
}

void add(size_t n) {
    size_t now = g_used.fetch_add(n) + n, peak = g_peak.load();
    while (now > peak && !g_peak.compare_exchange_weak(peak, now)) {}
}

void sub(size_t n) {
    size_t cur = g_used.load();
    while (!g_used.compare_exchange_weak(cur, cur > n ? cur - n : 0)) {}   // frees of memory allocated outside the wrap
}
}  // namespace

extern "C" size_t vp__alloc_used(void) { return g_used.load(); }
extern "C" size_t vp__alloc_peak(void) { return g_peak.load(); }
extern "C" size_t vp__alloc_budget(void) { return budget(); }
extern "C" int vp__alloc_oom(void) { return g_oom.load(); }

#ifdef VP_WRAP_MALLOC
extern "C" {
void* __real_malloc(size_t);
void* __real_calloc(size_t, size_t);
void* __real_realloc(void*, size_t);
void __real_free(void*);

void* __wrap_malloc(size_t n) {
    if (!admit(n)) return nullptr;
    void* p = __real_malloc(n);
    if (p) add(VP_USABLE(p));
    return p;
}
void* __wrap_calloc(size_t a, size_t b) {
    if (b && a > (size_t)-1 / b) return nullptr;
    if (!admit(a * b)) return nullptr;
    void* p = __real_calloc(a, b);
    if (p) add(VP_USABLE(p));
    return p;
}
void* __wrap_realloc(void* old, size_t n) {
    size_t before = old ? VP_USABLE(old) : 0;
    if (n > before && !admit(n - before)) return nullptr;
    void* p = __real_realloc(old, n);
    if (p || n == 0) {
        sub(before);
        if (p) add(VP_USABLE(p));
    }
    return p;
}
void __wrap_free(void* p) {
    if (p) sub(VP_USABLE(p));
    __real_free(p);
}
}
// new/delete go through malloc/free, which the linker redirects to the wrappers above
static void* vp_new(size_t n) {
    void* p = std::malloc(n ? n : 1);
    if (!p) throw std::bad_alloc();
    return p;
}
static void vp_delete(void* p) noexcept { std::free(p); }
#else
static void* vp_new(size_t n) {
    if (!n) n = 1;
    if (!admit(n)) throw std::bad_alloc();
    void* p = std::malloc(n);
    if (!p) throw std::bad_alloc();
    add(VP_USABLE(p));
    return p;
}
static void vp_delete(void* p) noexcept {
    if (p) sub(VP_USABLE(p));
    std::free(p);
}
#endif

void* operator new(size_t n) { return vp_new(n); }
void* operator new[](size_t n) { return vp_new(n); }
void* operator new(size_t n, const std::nothrow_t&) noexcept {
    try { return vp_new(n); } catch (...) { return nullptr; }
}
void* operator new[](size_t n, const std::nothrow_t&) noexcept {
    try { return vp_new(n); } catch (...) { return nullptr; }
}
void operator delete(void* p) noexcept { vp_delete(p); }
void operator delete[](void* p) noexcept { vp_delete(p); }
void operator delete(void* p, size_t) noexcept { vp_delete(p); }
void operator delete[](void* p, size_t) noexcept { vp_delete(p); }
void operator delete(void* p, const std::nothrow_t&) noexcept { vp_delete(p); }
void operator delete[](void* p, const std::nothrow_t&) noexcept { vp_delete(p); }
