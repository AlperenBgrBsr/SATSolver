#include "SATSolver.hpp"
#include <iostream>

using namespace std;

int main(int argc, char** argv) {
    if (argc < 2) {
        cerr << "usage: " << argv[0] << " <instance.cnf>" << endl;
        return 1;
    }

    SATSolver solver;
    bool sat = solver.solve(argv[1]);

    if (!sat) {
        cout << "s UNSATISFIABLE" << endl;
        return 20;
    }

    cout << "s SATISFIABLE" << endl;
    cout << "v";
    for (int v = 0; v < solver.num_vars(); v++) {
        cout << " " << (solver.model_value(v) ? (v + 1) : -(v + 1));
    }
    cout << " 0" << endl;

    return 10;
}
