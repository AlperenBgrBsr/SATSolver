#include "SATSolver.hpp"
#include <cstdio>
#include <cstdlib>
#include <random>

typedef vector<vector<int>> Formula;

static Formula generate(int n, int m, std::mt19937& rng) {
    Formula cls;
    for (int i = 0; i < m; i++) {
        int a, b, c;
        do {
            a = rng() % n;
            b = rng() % n;
            c = rng() % n;
        } while (a == b || b == c || a == c);

        vector<int> cl;
        cl.push_back((a + 1) * ((rng() & 1) ? 1 : -1));
        cl.push_back((b + 1) * ((rng() & 1) ? 1 : -1));
        cl.push_back((c + 1) * ((rng() & 1) ? 1 : -1));
        cls.push_back(cl);
    }
    return cls;
}

static bool brute_force(int n, const Formula& cls) {
    for (unsigned mask = 0; mask < (1u << n); mask++) {
        bool all_sat = true;
        for (size_t i = 0; i < cls.size() && all_sat; i++) {
            bool sat = false;
            for (size_t k = 0; k < cls[i].size(); k++) {
                int d   = cls[i][k];
                int var = abs(d) - 1;
                bool val = (mask >> var) & 1u;
                if ((d > 0) == val) { sat = true; break; }
            }
            if (!sat) all_sat = false;
        }
        if (all_sat) return true;
    }
    return false;
}

static bool model_ok(SATSolver& s, const Formula& cls) {
    for (size_t i = 0; i < cls.size(); i++) {
        bool sat = false;
        for (size_t k = 0; k < cls[i].size(); k++) {
            int d = cls[i][k];
            if (s.model_value(abs(d) - 1) == (d > 0)) { sat = true; break; }
        }
        if (!sat) return false;
    }
    return true;
}

static void write_cnf(const char* path, int n, const Formula& cls) {
    FILE* f = fopen(path, "w");
    if (!f) { perror(path); exit(1); }
    fprintf(f, "p cnf %d %zu\n", n, cls.size());
    for (size_t i = 0; i < cls.size(); i++) {
        for (size_t k = 0; k < cls[i].size(); k++) fprintf(f, "%d ", cls[i][k]);
        fprintf(f, "0\n");
    }
    fclose(f);
}

int main(int argc, char** argv) {
    int      count = (argc > 1) ? atoi(argv[1]) : 1000;
    unsigned seed0 = (argc > 2) ? (unsigned)strtoul(argv[2], 0, 10) : 1;

    int sat = 0, unsat = 0, mismatch = 0, bad_model = 0;

    for (int t = 0; t < count; t++) {
        unsigned seed = seed0 + t;
        std::mt19937 rng(seed);

        int    n     = 4 + rng() % 11;
        double ratio = 3.0 + (rng() % 300) / 100.0;
        int    m     = (int)(n * ratio);
        if (m < 1) m = 1;

        Formula cls = generate(n, m, rng);
        write_cnf("fuzz_tmp.cnf", n, cls);

        SATSolver s;
        bool got  = s.solve("fuzz_tmp.cnf");
        bool want = brute_force(n, cls);

        bool ok = (got == want);
        if (ok && got && !model_ok(s, cls)) { ok = false; bad_model++; }

        if (got) sat++;
        else     unsat++;

        if (!ok) {
            mismatch++;
            char out[128];
            snprintf(out, sizeof out, "fuzz-fail-%u.cnf", seed);
            write_cnf(out, n, cls);
            printf("MISMATCH seed=%u n=%d m=%d ratio=%.2f  solver=%s  truth=%s  saved %s\n",
                   seed, n, m, ratio, got ? "SAT" : "UNSAT", want ? "SAT" : "UNSAT", out);
        }
    }

    remove("fuzz_tmp.cnf");
    printf("tested=%d  sat=%d  unsat=%d  mismatches=%d  bad_models=%d\n",
           count, sat, unsat, mismatch, bad_model);
    return mismatch ? 1 : 0;
}
