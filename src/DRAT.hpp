#pragma once

#include <iostream>
#include <fstream>
#include <string>
#include <vector>

using namespace std;

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
