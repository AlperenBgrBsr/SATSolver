#include "SATSolver.hpp"

using namespace std;

// Defined with the invariant checker at the bottom of this file. Forward
// declared so reduceDB() can assert the one thing its remap depends on.
static void inv_fail(const char* where, const string& msg);

int SATSolver::decision_level() {
    return (int)trail_lim.size();
}

void SATSolver::new_decision_level() {
    trail_lim.push_back((int)trail.size());
}

int SATSolver::pick_branch_lit() {
    int best = -1;

    for (int v = 0; v < var_count; v++) {
        if (assignments[v] != -1) continue;
        if (best == -1 || activity[v] > activity[best]) best = v;
    }

    if (best == -1) return -1;

    return (best << 1) | (saved_phase[best] ? 0 : 1);
}

vector<int> SATSolver::analyze(int conflict_index, int& backjump_level, int& lbd) {
    int temp_head = (int)trail.size() - 1;
    int current_count = 0;
    int new_lbd = 0;
    clauses[conflict_index].touched = stats.conflicts;

    const vector<int>& conflict_clause = clauses[conflict_index].lits;
    vector<int> out_learnt;

    current_epoch++;
    for (size_t i = 0; i < conflict_clause.size(); i++) {
        int l = conflict_clause[i];
        int v = l >> 1;
       

        if (stamp[level[v]] != current_epoch) {
            stamp[level[v]] = current_epoch;
            new_lbd++;
        }

        if (level[v] == 0 || seen[v] == 1) {
            continue;
        }

        if (level[v] == decision_level()) {
            current_count++;
            activity[v] += var_inc;
            seen[v] = 1;
            to_clear.push_back(v);
        }
        else {
            seen[v] = 1;
            to_clear.push_back(v);
            activity[v] += var_inc;
            out_learnt.push_back(l);
        }
    }
    if (new_lbd + 1 < clauses[conflict_index].lbd) {
        if (clauses[conflict_index].lbd > 2 && new_lbd <= 2) stats.lbd_promotions++;
        clauses[conflict_index].lbd = new_lbd;
        stats.lbd_updates++;
    }
   



    while (current_count > 1) {
        int l = trail[temp_head];
        int v = l >> 1;

        if (seen[v] == 0 || level[v] == 0) {
            temp_head--;
            continue;
        }

        seen[v] = 0;
        current_count--;

        const vector<int>& reason_clause = clauses[reason[v]].lits;
        clauses[reason[v]].touched = stats.conflicts;

        current_epoch++;
        new_lbd = 0;

        for (size_t i = 1; i < reason_clause.size(); i++) {
            int l = reason_clause[i];
            int v = l >> 1;

            if (stamp[level[v]] != current_epoch) {
                stamp[level[v]] = current_epoch;
                new_lbd++;
            }

            if (level[v] == 0 || seen[v] == 1) {
                continue;
            }

            if (level[v] == decision_level()) {
                current_count++;
                activity[v] += var_inc;
                seen[v] = 1;
                to_clear.push_back(v);
            }
            else {
                seen[v] = 1;
                to_clear.push_back(v);
                activity[v] += var_inc;
                out_learnt.push_back(l);
            }
        }

        if (new_lbd + 1 < clauses[reason[v]].lbd) {
            if (clauses[reason[v]].lbd > 2 && new_lbd <= 2) stats.lbd_promotions++;
            clauses[reason[v]].lbd = new_lbd;
            stats.lbd_updates++;
        }

        temp_head--;
    }
    new_lbd = 1;
    current_epoch += 2;
    int uip;

    for (int i = temp_head; i >= 0; i--) {
        if (seen[trail[i] >> 1] == 1) {
            uip = trail[i] ^ 1;
            out_learnt.insert(out_learnt.begin(), uip);
            break;
        }
    }

    int highest_level = 0;
    size_t highest_lit_idx = 1;

    for (size_t i = 1; i < out_learnt.size(); i++) {
        if (level[out_learnt[i] >> 1] > highest_level) {
            highest_level = level[out_learnt[i] >> 1];
            highest_lit_idx = i;
        }

        if (stamp[level[out_learnt[i] >> 1]] != current_epoch) {
            stamp[level[out_learnt[i] >> 1]] = current_epoch;
            new_lbd++;
        }

    }

    if (out_learnt.size() > 1) {
        swap(out_learnt[1], out_learnt[highest_lit_idx]);
    }

    backjump_level = highest_level;
    lbd = new_lbd;

    for (int v : to_clear) seen[v] = 0;
    to_clear.clear();
    var_inc /= var_decay;

    if (var_inc > 1e100) {
        for (int v = 0; v < var_count; v++) {
            activity[v] *= 1e-100;
        }
        var_inc *= 1e-100;
    }

    

    return out_learnt;
}

void SATSolver::cancel_until(int lvl) {
    if (decision_level() <= lvl) return;

    int trail_index = trail_lim[lvl];
    int start_index = (int)trail.size() - 1;

    while (start_index >= trail_index) {
        int lit = trail[start_index--];
        int var = lit >> 1;

        saved_phase[var] = assignments[var];
        level[var] = -1;
        assignments[var] = -1;
        reason[var] = -1;
    }

    trail.resize(trail_index);
    trail_lim.resize(lvl);
    qhead = (int)trail.size();
}

void SATSolver::add_clause(vector<int>& lits) {
    if (lits.empty()) {
        cout << "UNSAT" << endl;
        exit(0);
    }

    clauses.push_back(Clause{lits});

    if (lits.size() == 1) {
        if (!enqueue(lits[0], -1)) root_unsat = true;
    }
    else {
        watches[lits[0]].push_back((int)clauses.size() - 1);
        watches[lits[1]].push_back((int)clauses.size() - 1);
    }
}

void SATSolver::resize_all(int n) {
    assignments.assign(n, -1);
    reason.assign(n, -1);
    level.assign(n, -1);
    seen.assign(n, 0);
    saved_phase.assign(n, 0);
    activity.assign(n, 0.0);
    stamp.assign(n+1,0);

    watches.assign(2 * n, {});
    clauses.clear();

    qhead = 0;
    num_problem_clauses = 0;
    current_epoch = 0;
    root_unsat = false;
    stats = Stats();
    trail.clear();
    trail.reserve(n);
    trail_lim.clear();
    trail_lim.reserve(n);
    to_clear.clear();
    to_clear.reserve(n);
   
}

int SATSolver::dimacs_cnf_to_lit(int dimacs_val) {
    int var = abs(dimacs_val) - 1;

    if (dimacs_val > 0) {
        return var << 1;
    }
    else {
        return (var << 1) | 1;
    }
}

static bool parse_dimacs_int(const string& s, int& out) {
    if (s.empty()) return false;

    size_t k = (s[0] == '-' || s[0] == '+') ? 1 : 0;
    if (k == s.size()) return false;
    if (s.size() - k > 9) return false;

    for (size_t d = k; d < s.size(); d++) {
        if (s[d] < '0' || s[d] > '9') return false;
    }

    out = stoi(s);
    return true;
}

void SATSolver::parse(const string& filename) {
    std::ifstream in(filename);

    if (!in.is_open()) {
        std::cerr << "Error: Could not open file " << filename << std::endl;
        exit(1);
    }

    string tmp;
    vector<int> current_clause;
    bool header_seen = false;

    while (in >> tmp) {
        if (tmp == "c") {
            getline(in, tmp);
        }
        else if (tmp == "%") {
            break;
        }
        else if (tmp == "p") {
            in >> tmp;

            int n_vars, n_clauses;
            if (!(in >> n_vars >> n_clauses) || n_vars < 0) {
                std::cerr << "Error: malformed p line in " << filename << std::endl;
                exit(1);
            }

            var_count = n_vars;
            resize_all(n_vars);
            header_seen = true;
        }
        else {
            int dimacs_val;
            if (!parse_dimacs_int(tmp, dimacs_val)) {
                continue;
            }

            if (dimacs_val == 0) {
                if (!current_clause.empty()) {
                    add_clause(current_clause);
                    current_clause.clear();
                }
            }
            else {
                if (!header_seen) {
                    std::cerr << "Error: clause before p line in " << filename << std::endl;
                    exit(1);
                }

                if (abs(dimacs_val) > var_count) {
                    std::cerr << "Error: variable " << abs(dimacs_val)
                              << " exceeds the declared count " << var_count << std::endl;
                    exit(1);
                }

                current_clause.push_back(dimacs_cnf_to_lit(dimacs_val));
            }
        }
    }

    if (!current_clause.empty()) {
        add_clause(current_clause);
        current_clause.clear();
    }

    num_problem_clauses = (int)clauses.size();
}

int SATSolver::value(int lit) {
    int var_state = assignments[lit >> 1];

    if (var_state == -1) {
        return -1;
    }

    if ((lit & 1) == 0) {
        return var_state;
    }
    else {
        return var_state ^ 1;
    }
}

int SATSolver::propagate() {
    while (qhead < (int)trail.size()) {
        int lit = trail[qhead++];
        int false_lit = lit ^ 1;

        stats.propagations++;

        vector<int>& idxs = watches[false_lit];

        int i = 0;
        int j = 0;

        while (i < (int)idxs.size()) {
            int current_idx = idxs[i++];
            Clause& current_clause = clauses[current_idx];

            stats.clause_visits++;

            if (current_clause.lits[0] == false_lit) {
                swap(current_clause.lits[0], current_clause.lits[1]);
            }

            if (value(current_clause.lits[0]) == 1) {
                idxs[j++] = current_idx;
                continue;
            }

            bool replacement_found = false;

            for (int k = 2; k < (int)current_clause.lits.size(); k++) {
                if (value(current_clause.lits[k]) != 0) {
                    replacement_found = true;
                    swap(current_clause.lits[1], current_clause.lits[k]);
                    watches[current_clause.lits[1]].push_back(current_idx);
                    break;
                }
            }

            if (replacement_found) {
                continue;
            }

            idxs[j++] = current_idx;

            if (value(current_clause.lits[0]) == 0) {
                while (i < (int)idxs.size()) {
                    idxs[j++] = idxs[i++];
                }

                idxs.resize(j);
                return current_idx;
            }
            else {
                if (!enqueue(current_clause.lits[0], current_idx)) {
                    while (i < (int)idxs.size()) {
                        idxs[j++] = idxs[i++];
                    }

                    idxs.resize(j);
                    return current_idx;
                }
            }
        }

        idxs.resize(j);
    }

    return -1;
}

bool SATSolver::enqueue(int lit, int forcing_clause_idx) {
    int var = lit >> 1;

    if (assignments[var] != -1) {
        if (value(lit) == 1) {
            return true;
        }
        else {
            return false;
        }
    }

    assignments[var] = !(lit & 1);
    reason[var] = forcing_clause_idx;
    level[var] = decision_level();
    trail.push_back(lit);

    return true;
}

void SATSolver::reduceDB() {
    vector<int> to_remove;
    vector<char> doomed;
    vector<int> reason_remap;

    for (int i = num_problem_clauses; i < (int)clauses.size(); i++) {
        if (clauses[i].lbd <= 2 || reason[(clauses[i].lits[0]) >> 1] == i) {
            continue;
        }
        to_remove.push_back(i);
    }

    doomed.assign(clauses.size(),0);
    reason_remap.assign(clauses.size(),0);

    // Identity everywhere to start with: a clause that does not move maps to
    // itself. The sweep overwrites the learnt region; the problem-clause region
    // keeps the identity, which is correct because those never move.
    for (int i = 0; i < (int)reason_remap.size(); i++) {
        reason_remap[i] = i;
    }

    sort(to_remove.begin(), to_remove.end(), [this](const int& i, const int& j) {
        if (clauses[i].lbd != clauses[j].lbd) {
            return clauses[i].lbd > clauses[j].lbd; // Primary sort
        }
        return clauses[i].touched < clauses[j].touched; // Secondary sort if primary is equal
    });

    for (int i = 0; i < (int)(to_remove.size() >> 1); i++) {
        doomed[to_remove[i]] = 1;
    }

    int i = num_problem_clauses;
    int j = i;

    long long removable    = (long long)to_remove.size();
    long long deleted      = 0;
    long long deleted_lits = 0;

    while (i < (int)clauses.size()) {
        if (doomed[i]) {
            reason_remap[i] = -1;

            // Sum the lengths here: resize() destroys these clauses and their
            // literal counts go with them.
            deleted++;
            deleted_lits += (long long)clauses[i].lits.size();
        }
        else {
            if (i != j) {
                clauses[j] = std::move(clauses[i]);
            }
            reason_remap[i] = j;
            j++;
        }
        i++;
    }

    clauses.resize(j);

    for (int v = 0; v < var_count; v++) {
        if (reason[v] != -1) {
            // The one assumption the whole remap rests on: a clause that is
            // some variable's reason was never a deletion candidate.
            if (reason_remap[reason[v]] == -1) {
                inv_fail("reduceDB", "var " + to_string(v) + " has reason "
                                     + to_string(reason[v]) + ", which was deleted");
            }

            reason[v] = reason_remap[reason[v]];
        }
    }

    watches.assign(2 * var_count,{});

    for (int i = 0; i < (int)clauses.size(); i++) {
        if (clauses[i].lits.size() < 2) {
            continue;
        }
        watches[clauses[i].lits[0]].push_back(i);
        watches[clauses[i].lits[1]].push_back(i);
    }

    stats.reduces++;
    stats.deleted     += deleted;
    stats.learnts     -= deleted;
    stats.learnt_lits -= deleted_lits;

    log_reduce(removable, deleted);
}


bool SATSolver::solve(const string& filename) {
    read_env();
    parse(filename);
    if (root_unsat) {
        return false;
    }

    if (check_every > 0) check_invariants("post-parse");

    int bt = 0;
    int lbd = 0;
    long long iters = 0;
    int interval = reduce_first;
    int next_reduce = reduce_first;

    while (true) {
        // The top of the loop is the one point where every structure is
        // settled: watch lists compacted, seen[] clear, trail consistent.

        if (stats.conflicts >= next_reduce) {
            reduceDB();
            interval += reduce_inc;
            next_reduce = stats.conflicts + interval;
        }

        if (check_every > 0 && (iters++ % check_every) == 0) {
            check_invariants("search");
        }

        int conflict = propagate();
        if (conflict != -1) {
            stats.conflicts++;
            if (decision_level() == 0) return false;
            vector<int> learnt = analyze(conflict, bt,lbd);
            cancel_until(bt);

            stats.learnts_total++;

            if (learnt.size() >= 2) {
                clauses.push_back(Clause{learnt,lbd,int(stats.conflicts)});
                int idx = clauses.size() - 1;
                watches[learnt[0]].push_back(idx);
                watches[learnt[1]].push_back(idx);
                enqueue(learnt[0],idx);

                stats.learnts++;
                stats.learnt_lits += (long long)learnt.size();
                if (stats.learnts > stats.max_learnts) stats.max_learnts = stats.learnts;

                stats.lbd_birth_sum += lbd;
                stats.lbd_birth_hist[lbd < LBD_BUCKETS ? lbd : LBD_BUCKETS - 1]++;
            }
            else {
                enqueue(learnt[0],-1);
            }

        }
        else {
            int lit = pick_branch_lit();
            if (lit == -1) return true;
            stats.decisions++;
            new_decision_level();
            enqueue(lit,-1);
        }
    }
}


// --- environment knobs ------------------------------------------------------
//
// Env vars rather than CLI flags: fuzz.cpp constructs a SATSolver directly and
// has no argv to thread a flag through, so this covers both binaries with no
// plumbing in either.

static long long env_ll(const char* name, long long dflt) {
    const char* s = getenv(name);
    if (s == nullptr || *s == '\0') return dflt;

    char* end = nullptr;
    long long v = strtoll(s, &end, 10);

    if (end == s || *end != '\0' || v < 0) {
        cerr << "Error: " << name << " must be a non-negative integer, got \""
             << s << "\"" << endl;
        exit(1);
    }

    return v;
}

void SATSolver::read_env() {
    reduce_first = env_ll("SAT_REDUCE_FIRST", 2000);
    reduce_inc   = env_ll("SAT_REDUCE_INC", 300);
    check_every  = env_ll("SAT_CHECK_EVERY", 0);
    log_reduces  = env_ll("SAT_LOG_REDUCES", 0) != 0;
}

// One line per reduce. The exit-time totals say where the database ended up;
// this says how it got there, which is the part that tells you whether the
// policy is holding or the core is saturating.
void SATSolver::log_reduce(long long removable, long long deleted) const {
    if (!log_reduces) return;

    long long held = (long long)clauses.size() - num_problem_clauses;
    long long glue = 0;

    for (size_t i = (size_t)num_problem_clauses; i < clauses.size(); i++) {
        if (clauses[i].lbd <= 2) glue++;
    }

    cout << "c reduce "     << stats.reduces
         << " conflicts "   << stats.conflicts
         << " before "      << (held + deleted)
         << " removable "   << removable
         << " protected "   << (held + deleted - removable)
         << " deleted "     << deleted
         << " held "        << held
         << " glue "        << glue
         << endl;
}

void SATSolver::print_stats(ostream& os) const {
    os << "c vars           " << var_count << "\n";
    os << "c clauses        " << num_problem_clauses << "\n";
    os << "c conflicts      " << stats.conflicts << "\n";
    os << "c decisions      " << stats.decisions << "\n";
    os << "c propagations   " << stats.propagations << "\n";
    os << "c clause_visits  " << stats.clause_visits << "\n";
    os << "c learnts_total  " << stats.learnts_total << "\n";
    os << "c learnts        " << stats.learnts << "\n";
    os << "c max_learnts    " << stats.max_learnts << "\n";
    os << "c learnt_lits    " << stats.learnt_lits << "\n";
    os << "c reduces        " << stats.reduces << "\n";
    os << "c deleted        " << stats.deleted << "\n";
    os << "c reduce_first   " << reduce_first << "\n";
    os << "c reduce_inc     " << reduce_inc << "\n";

    // Held distribution, recomputed here rather than maintained incrementally -
    // it is read once, at exit, and a stale incremental count would be worse
    // than no count at all.
    long long held[LBD_BUCKETS] = {};
    long long held_glue = 0;

    for (size_t i = (size_t)num_problem_clauses; i < clauses.size(); i++) {
        int l = clauses[i].lbd;
        held[l < LBD_BUCKETS ? (l < 0 ? 0 : l) : LBD_BUCKETS - 1]++;
        if (l <= 2) held_glue++;
    }

    long long birth_glue = stats.lbd_birth_hist[1] + stats.lbd_birth_hist[2];

    os << "c lbd_updates    " << stats.lbd_updates << "\n";
    os << "c lbd_promotions " << stats.lbd_promotions << "\n";
    os << "c lbd_birth_sum  " << stats.lbd_birth_sum << "\n";
    os << "c lbd_birth_glue " << birth_glue << "\n";
    os << "c lbd_held_glue  " << held_glue << "\n";

    os << "c lbd_birth_hist";
    for (int i = 1; i < LBD_BUCKETS; i++) {
        if (stats.lbd_birth_hist[i]) {
            os << " " << i << (i == LBD_BUCKETS - 1 ? "+" : "") << ":" << stats.lbd_birth_hist[i];
        }
    }
    os << "\n";

    os << "c lbd_held_hist ";
    for (int i = 1; i < LBD_BUCKETS; i++) {
        if (held[i]) {
            os << " " << i << (i == LBD_BUCKETS - 1 ? "+" : "") << ":" << held[i];
        }
    }
    os << "\n";
}

// --- invariant checker ------------------------------------------------------
//
// Compiled into every build but gated on SAT_CHECK_EVERY, which defaults to 0.
// The cost when off is one compare per search iteration, so release builds stay
// usable for the instances too slow to run under a debug build.

static void inv_fail(const char* where, const string& msg) {
    cerr << "INVARIANT VIOLATION [" << where << "]: " << msg << endl;
    abort();
}

void SATSolver::check_invariants(const char* where) {
    const int nclauses = (int)clauses.size();
    const int nlits = 2 * var_count;

    // 1. Every clause is non-empty and holds literals inside the encoding.
    for (int i = 0; i < nclauses; i++) {
        const vector<int>& c = clauses[i].lits;

        if (c.empty()) {
            inv_fail(where, "clause " + to_string(i) + " is empty");
        }

        for (size_t k = 0; k < c.size(); k++) {
            if (c[k] < 0 || c[k] >= nlits) {
                inv_fail(where, "clause " + to_string(i) + " holds literal "
                                + to_string(c[k]) + ", outside [0," + to_string(nlits) + ")");
            }
        }
    }

    // 2. Every watch entry is a live clause index that watches the literal it
    //    is filed under, and it is filed under lits[0] or lits[1] only.
    vector<int> on0(nclauses, 0);
    vector<int> on1(nclauses, 0);

    for (int l = 0; l < nlits; l++) {
        for (size_t k = 0; k < watches[l].size(); k++) {
            int idx = watches[l][k];

            if (idx < 0 || idx >= nclauses) {
                inv_fail(where, "watches[" + to_string(l) + "] holds clause index "
                                + to_string(idx) + ", outside [0," + to_string(nclauses) + ")");
            }

            const vector<int>& c = clauses[idx].lits;

            if (c.size() < 2) {
                inv_fail(where, "unit clause " + to_string(idx) + " appears in watches["
                                + to_string(l) + "]");
            }

            if (c[0] == l)      on0[idx]++;
            else if (c[1] == l) on1[idx]++;
            else {
                inv_fail(where, "clause " + to_string(idx) + " is filed under watches["
                                + to_string(l) + "] but watches neither lits[0]="
                                + to_string(c[0]) + " nor lits[1]=" + to_string(c[1]));
            }
        }
    }

    // 3. ...and conversely, every non-unit clause is watched exactly twice.
    for (int i = 0; i < nclauses; i++) {
        const vector<int>& c = clauses[i].lits;

        if (c.size() < 2) {
            if (on0[i] != 0 || on1[i] != 0) {
                inv_fail(where, "unit clause " + to_string(i) + " is watched");
            }
            continue;
        }

        // A clause whose first two literals are the same sits twice in one list.
        if (c[0] == c[1]) {
            if (on0[i] + on1[i] != 2) {
                inv_fail(where, "clause " + to_string(i) + " has lits[0]==lits[1] but "
                                + to_string(on0[i] + on1[i]) + " watch entries, expected 2");
            }
            continue;
        }

        if (on0[i] != 1) {
            inv_fail(where, "clause " + to_string(i) + " has " + to_string(on0[i])
                            + " watch entries on lits[0], expected 1");
        }
        if (on1[i] != 1) {
            inv_fail(where, "clause " + to_string(i) + " has " + to_string(on1[i])
                            + " watch entries on lits[1], expected 1");
        }
    }

    // 4. Trail, decision levels and the propagation cursor agree.
    if (qhead < 0 || qhead > (int)trail.size()) {
        inv_fail(where, "qhead " + to_string(qhead) + " outside [0," + to_string(trail.size()) + "]");
    }

    for (size_t i = 0; i < trail_lim.size(); i++) {
        if (trail_lim[i] < 0 || trail_lim[i] > (int)trail.size()) {
            inv_fail(where, "trail_lim[" + to_string(i) + "]=" + to_string(trail_lim[i])
                            + " outside [0," + to_string(trail.size()) + "]");
        }
        if (i > 0 && trail_lim[i - 1] > trail_lim[i]) {
            inv_fail(where, "trail_lim is not non-decreasing at " + to_string(i));
        }
    }

    int assigned = 0;
    for (int v = 0; v < var_count; v++) {
        if (assignments[v] != -1) assigned++;
    }
    if (assigned != (int)trail.size()) {
        inv_fail(where, to_string(assigned) + " assigned variables but trail holds "
                        + to_string(trail.size()));
    }

    // trail_lim is non-decreasing, so the level walks forward with the trail.
    int lvl = 0;
    for (size_t i = 0; i < trail.size(); i++) {
        while (lvl < (int)trail_lim.size() && trail_lim[lvl] <= (int)i) lvl++;

        int lit = trail[i];

        if (lit < 0 || lit >= nlits) {
            inv_fail(where, "trail[" + to_string(i) + "]=" + to_string(lit) + " is not a literal");
        }
        if (value(lit) != 1) {
            inv_fail(where, "trail[" + to_string(i) + "]=" + to_string(lit) + " is not true");
        }
        if (level[lit >> 1] != lvl) {
            inv_fail(where, "trail[" + to_string(i) + "] has level " + to_string(level[lit >> 1])
                            + ", but sits in level " + to_string(lvl) + " of the trail");
        }
    }

    // 5. Unassigned variables carry no residue, and every reason clause really
    //    does imply its variable.
    for (int v = 0; v < var_count; v++) {
        if (assignments[v] == -1) {
            if (reason[v] != -1) {
                inv_fail(where, "unassigned var " + to_string(v) + " keeps reason " + to_string(reason[v]));
            }
            if (level[v] != -1) {
                inv_fail(where, "unassigned var " + to_string(v) + " keeps level " + to_string(level[v]));
            }
            continue;
        }

        int r = reason[v];
        if (r == -1) continue;

        if (r < 0 || r >= nclauses) {
            inv_fail(where, "var " + to_string(v) + " has reason " + to_string(r)
                            + ", outside [0," + to_string(nclauses) + ")");
        }

        const vector<int>& c = clauses[r].lits;

        if ((c[0] >> 1) != v) {
            inv_fail(where, "reason " + to_string(r) + " of var " + to_string(v)
                            + " has lits[0]=" + to_string(c[0]) + ", a different variable");
        }
        if (value(c[0]) != 1) {
            inv_fail(where, "reason " + to_string(r) + " of var " + to_string(v)
                            + " does not have its implied literal true");
        }

        int max_other = 0;
        for (size_t k = 1; k < c.size(); k++) {
            if (value(c[k]) != 0) {
                inv_fail(where, "reason " + to_string(r) + " of var " + to_string(v)
                                + " has non-false literal " + to_string(c[k]) + " at index " + to_string(k));
            }
            if (level[c[k] >> 1] > max_other) max_other = level[c[k] >> 1];
        }

        // The clause is propagated the moment it becomes unit, so the implied
        // variable lands on the level of the last literal that falsified it.
        if (level[v] != max_other) {
            inv_fail(where, "var " + to_string(v) + " sits at level " + to_string(level[v])
                            + " but its reason " + to_string(r) + " is falsified up to level "
                            + to_string(max_other));
        }
    }

    // 6. LBD conventions. Problem clauses keep the sentinel; learnt clauses
    //    carry a real measurement, bounded below by 1 and above by their own
    //    length. Note the floor is 1, not 2: a clause is born with at least
    //    two blocks, but an in-place update can lower it to 1 if every literal
    //    has since collapsed onto a single decision level.
    for (int i = 0; i < nclauses; i++) {
        const Clause& c = clauses[i];

        if (i < num_problem_clauses) {
            if (c.lbd != 0) {
                inv_fail(where, "problem clause " + to_string(i) + " has lbd "
                                + to_string(c.lbd) + ", expected the 0 sentinel");
            }
            continue;
        }

        if (c.lbd < 1) {
            inv_fail(where, "learnt clause " + to_string(i) + " has lbd " + to_string(c.lbd));
        }
        if (c.lbd > (int)c.lits.size()) {
            inv_fail(where, "learnt clause " + to_string(i) + " has lbd " + to_string(c.lbd)
                            + " above its length " + to_string(c.lits.size()));
        }
    }

    // 7. analyze() clears up after itself.
    if (!to_clear.empty()) {
        inv_fail(where, "to_clear holds " + to_string(to_clear.size()) + " entries outside analyze()");
    }
    for (int v = 0; v < var_count; v++) {
        if (seen[v] != 0) {
            inv_fail(where, "seen[" + to_string(v) + "] is set outside analyze()");
        }
    }
}
