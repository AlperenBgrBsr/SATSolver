// Load-to-use latency ladder for this machine - the reference curve the
// solver's memory numbers are read against.
//
// 1. Effective core clock: a chain of dependent integer adds retires one per
//    cycle on Apple P-cores, so adds per second = Hz. Printed so a run that
//    landed on an E-core (much lower clock) is obvious rather than silent.
// 2. Pointer chase: a random cyclic permutation of 64-byte lines, so every
//    load depends on the previous one and the prefetcher cannot guess the
//    next address. Time per hop = latency of whichever level the buffer fits.
// 3. The same buffer walked in order, for contrast: the prefetcher hides most
//    of the latency, which is why an in-order layout (full17) behaves so much
//    better than its footprint suggests.
//
// Build and run (no solver code involved):
//   clang -O2 -o /tmp/latency_ladder tests/latency_ladder.c && /tmp/latency_ladder
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/sysctl.h>
#include <time.h>

static double now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC_RAW, &t);
    return t.tv_sec + t.tv_nsec * 1e-9;
}

static double clock_hz(void) {
    const long n = 2000000000L;
    double best = 1e9;
    for (int rep = 0; rep < 5; rep++) {
        uint64_t x = 1;
        double t0 = now();
        for (long i = 0; i < n; i += 8) {
            __asm__ volatile(
                "add %0, %0, #1\n add %0, %0, #1\n add %0, %0, #1\n add %0, %0, #1\n"
                "add %0, %0, #1\n add %0, %0, #1\n add %0, %0, #1\n add %0, %0, #1\n"
                : "+r"(x));
        }
        double dt = now() - t0;
        if (dt < best) best = dt;
    }
    return n / best;
}

static uint64_t rng_state = 0x9E3779B97F4A7C15ull;     // fixed seed: reproducible
static uint64_t rng(void) {
    rng_state ^= rng_state << 13;
    rng_state ^= rng_state >> 7;
    rng_state ^= rng_state << 17;
    return rng_state;
}

// Returns ns per hop; `random_order` 0 links the lines in address order.
static double chase(size_t bytes, int random_order) {
    size_t n = bytes / 64;
    if (n < 2) n = 2;
    char* buf = aligned_alloc(64, n * 64);
    size_t* perm = malloc(n * sizeof *perm);
    for (size_t i = 0; i < n; i++) perm[i] = i;
    if (random_order) {
        for (size_t i = n - 1; i > 0; i--) {
            size_t j = rng() % (i + 1);
            size_t t = perm[i]; perm[i] = perm[j]; perm[j] = t;
        }
    }
    for (size_t i = 0; i < n; i++)
        *(void**)(buf + perm[i] * 64) = buf + perm[(i + 1) % n] * 64;

    void** p = (void**)(buf + perm[0] * 64);
    for (size_t i = 0; i < 2 * n; i++) p = *p;           // warm caches and TLB

    const long hops = 20000000;
    double best = 1e9;
    for (int rep = 0; rep < 3; rep++) {
        double t0 = now();
        for (long i = 0; i < hops; i++) p = *p;
        double dt = now() - t0;
        if (dt < best) best = dt;
    }
    if (p == NULL) puts("");                              // keep the chain live
    free(perm);
    free(buf);
    return best / hops * 1e9;
}

static long long sysctl_ll(const char* name) {
    long long v = 0;
    size_t len = sizeof v;
    if (sysctlbyname(name, &v, &len, NULL, 0) != 0) return -1;
    return v;
}

int main(void) {
    printf("P-core L1d %lld KB, L2 %lld KB | E-core L1d %lld KB, L2 %lld KB | page %lld KB\n",
           sysctl_ll("hw.perflevel0.l1dcachesize") >> 10, sysctl_ll("hw.perflevel0.l2cachesize") >> 10,
           sysctl_ll("hw.perflevel1.l1dcachesize") >> 10, sysctl_ll("hw.perflevel1.l2cachesize") >> 10,
           sysctl_ll("hw.pagesize") >> 10);

    double hz = clock_hz();
    printf("effective clock %.3f GHz%s\n\n", hz / 1e9,
           hz < 3.0e9 ? "   <-- low: probably an E-core, rerun" : "");

    size_t kb[] = {16, 32, 64, 96, 128, 192, 256, 512, 1024, 2048, 4096, 8192,
                   12288, 16384, 24576, 32768, 65536, 131072, 262144, 524288};
    printf("%10s  %18s  %18s\n", "buffer", "random chase", "in-order walk");
    printf("%10s  %8s %9s  %8s %9s\n", "KB", "ns", "cycles", "ns", "cycles");
    for (size_t k = 0; k < sizeof kb / sizeof *kb; k++) {
        double r = chase(kb[k] << 10, 1);
        double s = chase(kb[k] << 10, 0);
        printf("%10zu  %8.2f %9.1f  %8.2f %9.1f\n", kb[k], r, r * hz / 1e9, s, s * hz / 1e9);
        fflush(stdout);
    }
    return 0;
}
