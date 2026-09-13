#pragma once

#include <iostream>
#include <fstream>
#include <string>
#include <vector>

using namespace std;

// DRAT proof emitter. One clause per line, DIMACS literals terminated by 0:
// additions bare, deletions prefixed "d ", and the proof closed by the empty
// clause. Inert unless open() is handed a non-empty path, so a run without
// SAT_PROOF set pays nothing.
class DRAT {
    public:
        void open(const string& path);
        void add(const vector<int>& lits_add);
        void del(const vector<int>& lits_del);
        void finish();
    private:
        static int lit_to_dimac(int lit);
        ofstream os;
        bool enabled = false;
};
