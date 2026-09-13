#include "DRAT.hpp"

#include <cstdlib>

using namespace std;


int DRAT::lit_to_dimac(int lit) {
    int var = lit >> 1;
    return (lit & 1) ? -(var + 1) : (var + 1);
}

void DRAT::open(const string& path) {
    if (path.empty()) return; 

    os.open(path);

    if (!os) {
        cerr << "Error: could not open proof file " << path << endl;
        exit(1);
    }

    enabled = true;
}


void DRAT::add(const vector<int>& lits_add) {
    if (!enabled) return;

    for (int lit : lits_add) {
        os << lit_to_dimac(lit) << ' ';
    }

    os << "0\n";
}

void DRAT::del(const vector<int>& lits_del) {
    if (!enabled) return;

    os << "d ";

    for (int lit : lits_del) {
        os << lit_to_dimac(lit) << ' ';
    }

    os << "0\n";
}

void DRAT::finish() {
    if (!enabled) return;

    os << "0\n";
    os.close();
    enabled = false;
}
