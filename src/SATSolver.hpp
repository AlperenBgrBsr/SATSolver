#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <cmath>

using namespace std;

class SATSolver {
private:
    struct Clause {
        vector<int> lits;
    };

    int qhead = 0;
    int var_count = 0;

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

    double var_inc = 1.0;
    double var_decay = 0.95;
    bool root_unsat = false;

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
    vector<int> analyze(int conflict_index, int& backjump_level);
public:
    bool solve(const string& filename);

    int  num_vars() const { return var_count; }
    bool model_value(int var) const { return assignments[var] != 0; }
};
