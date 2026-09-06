#include "SATSolver.hpp"

using namespace std;

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

vector<int> SATSolver::analyze(int conflict_index, int& backjump_level) {
    int temp_head = (int)trail.size() - 1;
    int current_count = 0;

    const vector<int>& conflict_clause = clauses[conflict_index].lits;
    vector<int> out_learnt;

    for (size_t i = 0; i < conflict_clause.size(); i++) {
        int l = conflict_clause[i];
        int v = l >> 1;

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

        for (size_t i = 1; i < reason_clause.size(); i++) {
            int l = reason_clause[i];
            int v = l >> 1;

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

        temp_head--;
    }

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
    }

    if (out_learnt.size() > 1) {
        swap(out_learnt[1], out_learnt[highest_lit_idx]);
    }

    backjump_level = highest_level;

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

    watches.assign(2 * n, {});
    clauses.clear();

    qhead = 0;
    root_unsat = false;
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

        vector<int>& idxs = watches[false_lit];

        int i = 0;
        int j = 0;

        while (i < (int)idxs.size()) {
            int current_idx = idxs[i++];
            Clause& current_clause = clauses[current_idx];

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


bool SATSolver::solve(const string& filename) {
    parse(filename);
    if (root_unsat) {
        return false;
    }
    int bt = 0;
    while (true) {
        int conflict = propagate();
        if (conflict != -1) {
            if (decision_level() == 0) return false;
            vector<int> learnt = analyze(conflict, bt);
            cancel_until(bt);

            if (learnt.size() >= 2) {
                clauses.push_back(Clause{learnt});
                int idx = clauses.size() - 1;
                watches[learnt[0]].push_back(idx);
                watches[learnt[1]].push_back(idx);
                enqueue(learnt[0],idx);
            }
            else {
                enqueue(learnt[0],-1);
            }

        }
        else {
            int lit = pick_branch_lit();
            if (lit == -1) return true;
            new_decision_level();
            enqueue(lit,-1);
        }
    }
}
