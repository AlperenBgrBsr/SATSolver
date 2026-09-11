#include <iostream>
#include <fstream>
#include <vector>
#include <algorithm>
#include <string>
#include <cmath>
#include <cstdlib>
#include <cstdint>

using namespace std;

class SATSolver {
private:
    struct Clause {
        vector<int> lits;
        int lbd = 0;
        int touched = 0;
    };

    // LBD histogram buckets. Bucket i counts clauses with lbd == i; the last
    // bucket is the overflow bin for everything at or above it. Bucket 0 is
    // never used - lbd 0 is the problem-clause sentinel, never a birth value.
    static const int LBD_BUCKETS = 32;

    // Counters. Purely observational: nothing here feeds back into the search,
    // so a wrong counter can never change a verdict.
    struct Stats {
        long long conflicts     = 0;
        long long decisions     = 0;
        long long propagations  = 0;   // trail literals dequeued in propagate()
        long long clause_visits = 0;   // clauses inspected in propagate()
        long long learnts_total = 0;   // clauses learnt over the whole run
        long long learnts       = 0;   // learnt clauses currently held
        long long max_learnts   = 0;   // high-water mark of the above
        long long learnt_lits   = 0;   // literals across the held learnt clauses
        long long reduces       = 0;   // reduceDB invocations
        long long deleted       = 0;   // learnt clauses removed

        long long lbd_updates   = 0;   // times an in-place LBD lowering fired
        long long lbd_promotions= 0;   // ...of those, ones that landed at lbd <= 2
        long long lbd_birth_sum = 0;   // sum of birth LBDs, for the mean

        long long lbd_birth_hist[LBD_BUCKETS] = {};
    };

    int qhead = 0;
    int var_count = 0;
    int num_problem_clauses = 0;
    uint32_t current_epoch = 0;

    vector<Clause> clauses;
    vector<vector<int>> watches;
    vector<int> trail;
    vector<int> trail_lim;
    vector<int> assignments;
    vector<int> reason;
    vector<int> level;
    vector<char> seen;
    vector<char> saved_phase;
    vector<double> activity;
    vector<int> to_clear;
    vector<uint32_t> stamp;

    double var_inc = 1.0;
    double var_decay = 0.95;
    bool root_unsat = false;

    Stats stats;

    // Clause-deletion schedule, read from the environment in solve(). Unused
    // until deletion exists; plumbed now so the baseline records the schedule
    // it was taken under.
    long long reduce_first = 2000;   // SAT_REDUCE_FIRST
    long long reduce_inc   = 300;    // SAT_REDUCE_INC
    long long check_every  = 0;      // SAT_CHECK_EVERY, 0 = off
    bool log_reduces       = false;  // SAT_LOG_REDUCES=1

    void read_env();

    void resize_all(int n);
    void parse(const string& filename);
    void add_clause(vector<int>& lits);
    int dimacs_cnf_to_lit(int dimacs_val);

    int value(int lit);
    bool enqueue(int lit, int reason);
    int propagate();

    int decision_level();
    void new_decision_level();
    void cancel_until(int level);

    int pick_branch_lit();
    vector<int> analyze(int conflict_index, int& backjump_level, int& lbd);

    void reduceDB();

    // Aborts on the first violation. Call only at quiescent points - not
    // inside propagate(), whose watch lists are mid-compaction, and not
    // inside analyze(), which leaves seen[] dirty until it returns.
    void check_invariants(const char* where);
public:
    bool solve(const string& filename);

    void print_stats(ostream& os) const;

    // Call at the end of reduceDB, after compaction. `removable` is how many
    // clauses were deletion candidates, `deleted` how many actually went. The
    // rest is read off the current state.
    void log_reduce(long long removable, long long deleted) const;

    int  num_vars() const { return var_count; }
    bool model_value(int var) const { return assignments[var] != 0; }
};
