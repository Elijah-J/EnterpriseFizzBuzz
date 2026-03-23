# Formal Model Checking Research Report

## 1. Temporal Logic: LTL vs CTL

**LTL (Linear Temporal Logic)** reasons over single infinite execution paths:
- **G(p)** (Globally): p holds in every state of the path
- **F(p)** (Finally/Eventually): p holds in some future state
- **X(p)** (neXt): p holds in the immediate successor state
- **U(p,q)** (Until): p holds continuously until q becomes true
- LTL has implicit universal path quantification: a formula must hold on ALL paths

**CTL (Computation Tree Logic)** reasons over branching trees with explicit path quantifiers:
- **A** (All paths) and **E** (Exists a path) must prefix every temporal operator
- **AG(p)**: invariant -- p holds everywhere on all paths
- **EF(p)**: reachability -- some path reaches a state satisfying p
- **AX(p)**: in all immediate successors, p holds
- **AU(p,q)** / **EU(p,q)**: until operators with universal/existential path quantification
- CTL model checking: O(|formula| * (|states| + |transitions|)) via bottom-up state labeling

## 2. State Space Exploration

A **state** is a complete assignment of all model variables. The state space forms a Kripke structure (directed graph): nodes are states, edges are **transitions** (atomic actions updating variables). An **initial state** set and **labeling function** (mapping states to true propositions) complete the structure.

- **BFS**: queue-based, finds shortest counterexamples, memory-intensive (stores full frontier). TLC (TLA+ model checker) uses BFS by default.
- **DFS**: stack-based, memory-efficient. SPIN uses DFS. Liveness checking uses **nested DFS** (two-phase DFS for accepting cycle detection in Buchi automata product).
- **State hashing**: states are canonicalized and stored in a hash set. Bitstate hashing (SPIN) trades completeness for massive memory savings.

## 3. Symmetry Reduction

Exploits automorphisms: if permuting component identities maps state s1 to s2, only one representative per equivalence class is explored.

- **Scalarsets**: declare interchangeable processes (e.g., N identical threads). The checker canonicalizes states by sorting symmetric components.
- **Implementation**: before inserting a state into the visited set, compute its canonical form (apply all permutations, take lexicographic minimum, or use sorted normal form). Only store the canonical representative.
- Reduces state space by up to N! for N symmetric components.
- Murphi pioneered scalarset symmetry reduction; TLC supports symmetry sets.

## 4. Partial Order Reduction (POR)

Prunes redundant interleavings of **independent** transitions. Two transitions are independent if: (1) both remain enabled regardless of execution order, and (2) executing in either order yields the same state.

- **Ample/stubborn sets**: at each state, expand only a sufficient subset of enabled transitions. Requirements: (a) non-empty if any transition enabled, (b) transitions outside the ample set are independent from those inside along the reduced path, (c) **cycle proviso** -- no transition is ignored forever on any cycle (prevents missing liveness violations).
- SPIN computes independence via static analysis of variable read/write sets.
- Can reduce exponential interleavings to near-linear in practice.

## 5. Counterexample Generation

When a property is violated, the checker reconstructs a **trace** from initial state to violation.

- **Safety (AG(p) fails)**: store parent pointers during BFS/DFS. Follow pointers from the violating state back to the initial state, then reverse. BFS yields shortest trace.
- **Liveness (GF(p) fails)**: the counterexample is a **lasso** -- a finite prefix reaching a cycle that repeats forever without satisfying the property. Found via nested DFS: first DFS finds accepting states, second DFS from each accepting state detects back-edges forming cycles.
- **Output format**: sequence of (state, action-label) pairs. The prefix shows how to reach the cycle; the cycle portion shows the infinite bad behavior.
