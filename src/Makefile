# Compiler settings
CXX      = clang++
CXXFLAGS = -std=c++17 -Wall -Wextra -g
EXTRA    =

# macOS SDK workaround. The Command Line Tools ship a libc++ newer than Apple
# clang 16 understands (__builtin_ctzg), so <iostream> fails to compile against
# the default SDK. Prefer an Xcode SDK when one is installed.
# Override with:  make SDK=/path/to/MacOSX15.2.sdk     (or  make SDK= )
XCODE_SDKS = /Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs
SDK       ?= $(firstword $(wildcard $(XCODE_SDKS)/MacOSX15.2.sdk $(XCODE_SDKS)/MacOSX15.sdk))
ifneq ($(SDK),)
CXXFLAGS += -isysroot $(SDK)
endif

# Target executable name
TARGET = sat

# Source files. main.cpp is picked up automatically once you create it.
SRCS = SATSolver.cpp $(wildcard main.cpp)
OBJS = $(SRCS:.cpp=.o)

# Header files (for dependency tracking)
HDRS = SATSolver.hpp

# Default rule: link once main.cpp exists, otherwise just compile what is here.
ifeq ($(wildcard main.cpp),)
all: $(OBJS)
	@echo "Compiled $(OBJS)."
	@echo "No main.cpp yet - create one and 'make' will link ./$(TARGET)."
else
all: $(TARGET)
endif

# Link the object files to create the executable
$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) $(EXTRA) -o $(TARGET) $(OBJS)

# Rebuild every object when the flag set changes, so a plain `make` after a
# `make check` / `make fuzz` does not try to link sanitized objects.
.build-mode: FORCE
	@echo '$(CXXFLAGS) $(EXTRA)' | cmp -s - $@ || echo '$(CXXFLAGS) $(EXTRA)' > $@
FORCE:

# Compile source files into object files
%.o: %.cpp $(HDRS) .build-mode
	$(CXX) $(CXXFLAGS) $(EXTRA) -c $< -o $@

# Checked build - use this while developing.
#
# Catches the out-of-bounds indexing this code is prone to: three index spaces
# (variable / literal / clause) all stored as plain int. libc++ hardening
# bounds-checks vector::operator[], which covers every array in the solver;
# UBSan covers the shift arithmetic the literal encoding is built on.
#
# NOT -fsanitize=address: on macOS 26 the clang 16 ASan runtime aborts during
# its own init ("CHECK failed: sanitizer_malloc_mac.inc ... asan_init_is_running")
# before main() runs, even for an empty program. Update Xcode, or install a
# matching LLVM, to use ASan here.
CHECKFLAGS = -fsanitize=undefined -fno-omit-frame-pointer \
             -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG

check:
	@$(MAKE) --no-print-directory clean
	@$(MAKE) --no-print-directory all EXTRA="$(CHECKFLAGS)"

# Regression suite: every instance under ../tests, with model verification.
test: $(TARGET)
	@python3 ../tests/run_tests.py

# Differential fuzzer: random 3-SAT, solver verdict vs exhaustive brute force.
#   make fuzz && ./fuzz [instances] [start_seed]
fuzz:
	@$(MAKE) --no-print-directory clean
	@$(MAKE) --no-print-directory fuzz-bin EXTRA="$(CHECKFLAGS)"

fuzz-bin: SATSolver.o fuzz.o
	$(CXX) $(CXXFLAGS) $(EXTRA) -o fuzz SATSolver.o fuzz.o

# Optimized build: no -g, asserts compiled out. Use this for timing runs only.
release:
	@$(MAKE) --no-print-directory clean
	@$(MAKE) --no-print-directory all CXXFLAGS="$(filter-out -g,$(CXXFLAGS)) -O2 -DNDEBUG"

# Benchmark instances. Generated, not vendored, and deliberately outside the
# regression suite - `make test` does not touch them. Take timings on a
# `make release` build; a -g or sanitized build measures the wrong thing.
#   make bench-gen                       regenerate tests/bench
#   make bench BENCHFLAGS="--timeout 60 --out ../tests/baseline.txt"
BENCHFLAGS ?= --timeout 60

bench-gen:
	@python3 ../tests/gen_bench.py

bench: $(TARGET)
	@python3 ../tests/bench.py $(BENCHFLAGS)

# make run CNF=../tests/uf20-91/uf20-01.cnf
CNF ?= ../tests/uf20-91/uf20-01.cnf
# The `-` ignores the exit status: 10 = SAT, 20 = UNSAT are successes here.
run: $(TARGET)
	-./$(TARGET) $(CNF)

# Clean up build files
clean:
	rm -f $(OBJS) $(TARGET) fuzz fuzz.o fuzz_tmp.cnf .build-mode
	rm -rf *.dSYM

.PHONY: all test check fuzz fuzz-bin release run clean bench bench-gen FORCE
