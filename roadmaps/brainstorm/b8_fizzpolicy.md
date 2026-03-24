# FizzPolicy -- Declarative Policy Engine

**Author:** Brainstorm Agent B8
**Date:** 2026-03-24
**Status:** PROPOSED

---

## The Problem

The Enterprise FizzBuzz Platform enforces access control, compliance, and operational constraints through five independent, hardcoded subsystems. The RBAC module (`auth.py`) embeds a five-tier role hierarchy with permission ranges baked into Python classes. The compliance module (`compliance.py`) hardcodes SOX segregation-of-duties rules, GDPR consent flow logic, and HIPAA minimum necessary levels as procedural Python code. The capability security module (`capability_security.py`) implements unforgeable object capabilities with a fixed operation enum. The network policy engine (`fizzcni.py`) evaluates ingress/egress rules through imperative `PolicyAction` and `PolicyDirection` enums. The approval workflow (`approval.py`) defines `PolicyType` enums and `ApprovalPolicy` dataclasses with hardcoded escalation logic.

These five systems share a common purpose -- determining whether a requested action is permitted -- but they share no common language, no common evaluation engine, no common audit trail, and no common management interface. When a new compliance requirement emerges (and they emerge frequently in a platform subject to SOX, GDPR, and HIPAA simultaneously), an engineer must identify which of the five subsystems is responsible, understand its internal control flow, write new Python code, add tests, and deploy the change. The policy is inseparable from the enforcement mechanism. You cannot read the platform's access control posture from a document; you must read five separate Python modules totaling thousands of lines and mentally reconstruct the policy from procedural logic scattered across conditional branches, enum values, and method chains.

This is the fundamental problem that the Open Policy Agent (OPA) project was created to solve. OPA decouples policy from code. Policies are written in a purpose-built language (Rego) that is declarative, auditable, testable, and deployable independently of the applications they govern. The policy engine evaluates queries against a policy document and a data document, producing a decision. The application asks "is this allowed?" and the engine answers based on the current policy, without the application needing to know anything about the policy's logic. Policy authors write policies. Application developers write admission checks. The two concerns are separated.

The Enterprise FizzBuzz Platform has no policy engine. It has five policy enforcement points, each with its own embedded policy logic, its own data model, its own evaluation semantics, and its own failure modes. The compliance module checks SOX rules one way. The RBAC module checks permissions another way. The capability security module checks authorities a third way. None of them can answer the question "given this request context, what are ALL the policies that apply, and what do they ALL say?" because they do not share a language, a data model, or an evaluation framework. The platform cannot express a policy that spans multiple enforcement domains (e.g., "requests from the audit role must have HIPAA clearance AND a valid capability token AND must not violate the network policy for the target service") because no single system can evaluate across all five domains.

In Open Policy Agent, this cross-domain policy is a single Rego rule:

```
allow {
    input.role == "audit"
    data.hipaa.clearance[input.user]
    data.capabilities.valid[input.token]
    not data.network_policy.denied[input.source][input.target]
}
```

Four domains. One rule. One evaluation. One decision log entry. One place to audit. The Enterprise FizzBuzz Platform needs this capability. Not as a replacement for the existing enforcement points -- those remain as the mechanisms that execute decisions -- but as the unified brain that makes them. FizzPolicy is that brain.

---

## The Vision

A complete declarative policy engine inspired by Open Policy Agent, implementing a Rego-inspired policy language (FizzRego), a multi-phase policy compiler, a high-performance evaluation engine, a versioned policy bundle system with cryptographic signing, comprehensive decision logging, external data integration, a policy testing framework, and integration points across the platform's authorization, compliance, network, capability, and admission control surfaces. FizzPolicy does not replace the RBAC module, the compliance module, the capability security module, the network policy engine, or the approval workflow. It unifies them. Each enforcement point delegates its decision to FizzPolicy, which evaluates the request against the current policy bundle and returns a structured decision with an explanation. The enforcement point then acts on the decision. Policy logic moves from Python code into FizzRego documents. Enforcement mechanisms remain in Python code. The separation is clean, auditable, and independently deployable.

---

## Key Components

- **`fizzpolicy.py`** (~3,500 lines): FizzPolicy Declarative Policy Engine

### FizzRego Policy Language

A purpose-built declarative policy language modeled on OPA's Rego, adapted for the FizzBuzz domain. FizzRego is a datalog-inspired language with the following constructs:

- **Packages**: Policies are organized into packages that mirror the platform's enforcement domains:
  ```
  package fizzbuzz.authz
  ```
  Packages define namespaces. A rule `allow` in package `fizzbuzz.authz` is referenced as `data.fizzbuzz.authz.allow`. Packages enable composition: the admission controller can evaluate `data.fizzbuzz.authz.allow AND data.fizzbuzz.compliance.approved AND data.fizzbuzz.network.permitted` by referencing rules from three separate packages.

- **Rules**: The fundamental unit of policy logic. Rules have a head (the value being computed) and a body (the conditions that must all be satisfied):
  ```
  default allow = false

  allow {
      input.role == "FIZZBUZZ_OPERATOR"
      input.action == "evaluate"
      input.number > 0
  }
  ```
  A rule with no body is unconditionally true. A rule with a body is true when every expression in the body is true. Multiple rules with the same head are logical OR: the head is true if ANY rule body is satisfied. The `default` keyword provides a fallback value when no rule matches.

- **Complete Rules**: Rules that assign a value to a variable:
  ```
  max_range = 1000 {
      input.role == "FIZZBUZZ_OPERATOR"
  }

  max_range = 100 {
      input.role == "FIZZBUZZ_ANALYST"
  }

  max_range = 10 {
      input.role == "ANONYMOUS"
  }
  ```
  Complete rules produce a single value. If multiple complete rules with the same head are satisfied, the evaluation engine raises a conflict error unless all matching rules produce the same value.

- **Partial Rules (Sets and Objects)**: Rules that incrementally build collections:
  ```
  permitted_ranges[range] {
      some role in data.roles
      role.name == input.role
      range := role.max_range
  }

  compliance_violations[violation] {
      some regime in ["SOX", "GDPR", "HIPAA"]
      not data.compliance.cleared[input.user][regime]
      required_for_action(input.action, regime)
      violation := {
          "regime": regime,
          "user": input.user,
          "action": input.action,
          "reason": sprintf("User %s lacks %s clearance for action %s", [input.user, regime, input.action]),
      }
  }
  ```
  Set rules (with `[element]`) build sets. Object rules (with `[key]`) build mappings. Each rule body that succeeds contributes one element or key-value pair to the collection.

- **Comprehensions**: Inline set, array, and object construction:
  ```
  high_risk_numbers := {n | some n in input.numbers; n > 100}
  formatted_results := [sprintf("FizzBuzz(%d) = %s", [n, r]) | some n, r in data.results]
  role_permissions := {role: perms | some role in data.roles; perms := data.permissions[role]}
  ```
  Comprehensions evaluate the body expression for each binding of the iteration variable and collect the results.

- **Negation**: The `not` keyword inverts a condition:
  ```
  allow {
      input.role == "FIZZBUZZ_OPERATOR"
      not suspended[input.user]
      not cognitive_overload
  }

  suspended[user] {
      some entry in data.suspension_list
      entry.user == user
      entry.expires_at > time.now()
  }

  cognitive_overload {
      data.operator.bob.cognitive_load > 70
  }
  ```
  Negation uses negation-as-failure semantics: `not p` is true when `p` cannot be proven true. Negation is safe only when the negated expression is grounded (all variables are bound by positive conditions elsewhere in the rule body). The compiler rejects rules with unsafe negation.

- **Unification**: The `:=` (assignment) and `==` (equality/unification) operators:
  ```
  allow {
      user := input.user
      role := data.user_roles[user]
      role == "FIZZBUZZ_SUPERUSER"
  }
  ```
  Unification binds variables to values and checks equality. The `some` keyword introduces local variables:
  ```
  allow {
      some user, role
      data.role_bindings[user] == role
      role == input.required_role
  }
  ```

- **With Keyword**: Override input or data for sub-evaluations:
  ```
  test_admin_allowed {
      allow with input as {"role": "FIZZBUZZ_SUPERUSER", "action": "evaluate", "number": 42}
  }
  ```
  The `with` keyword is primarily used in policy tests to inject mock input and data.

- **Every Keyword**: Universal quantification:
  ```
  all_compliant {
      every regime in ["SOX", "GDPR", "HIPAA"] {
          data.compliance.cleared[input.user][regime]
      }
  }
  ```
  `every` succeeds when the body is true for every binding of the iteration variable.

- **Imports**: Reference policies from other packages:
  ```
  import data.fizzbuzz.compliance as compliance
  import data.fizzbuzz.network as netpol

  allow {
      compliance.approved
      netpol.permitted
  }
  ```

- **Comments**: Single-line comments with `#`:
  ```
  # SOX requires segregation of duties: the evaluator cannot also be the approver
  allow {
      input.evaluator != input.approver
  }
  ```

### Policy Compiler

A multi-phase compiler that transforms FizzRego source text into an executable evaluation plan:

- **Lexer** (`FizzRegoLexer`): Tokenizes FizzRego source into a stream of tokens. Token types include: `PACKAGE`, `IMPORT`, `DEFAULT`, `NOT`, `SOME`, `EVERY`, `WITH`, `AS`, `IF`, `ELSE`, `TRUE`, `FALSE`, `NULL`, `IDENT` (identifiers), `STRING` (double-quoted strings), `NUMBER` (integers and floats), `LBRACE`, `RBRACE`, `LBRACKET`, `RBRACKET`, `LPAREN`, `RPAREN`, `DOT`, `COMMA`, `SEMICOLON`, `COLON`, `ASSIGN` (`:=`), `EQ` (`==`), `NEQ` (`!=`), `LT`, `GT`, `LTE`, `GTE`, `PLUS`, `MINUS`, `STAR`, `SLASH`, `PERCENT`, `PIPE`, `AMPERSAND`, `COMMENT`, `NEWLINE`, `EOF`. The lexer handles string escape sequences, multi-line strings (backtick-delimited), and number literals (decimal, hex `0x`, octal `0o`, binary `0b`). Lexer errors report the source location (file, line, column) for diagnostic messages.

- **Parser** (`FizzRegoParser`): Recursive descent parser that constructs an Abstract Syntax Tree (AST) from the token stream. The grammar follows Rego's precedence rules:
  - Lowest: `or` (multiple rule definitions with the same head)
  - `with` expressions
  - `not` negation
  - Comparison operators (`==`, `!=`, `<`, `>`, `<=`, `>=`)
  - Arithmetic operators (`+`, `-`, `*`, `/`, `%`)
  - Unary negation (`-`)
  - Dot access and bracket indexing
  - Highest: atoms (identifiers, literals, comprehensions, function calls)

  AST node types: `PackageNode`, `ImportNode`, `RuleNode` (head, body, default value), `ExprNode` (operator, operands), `TermNode` (reference, literal, comprehension), `RefNode` (chain of dot/bracket accesses), `ComprehensionNode` (set/array/object, term, body), `SomeNode` (local variable declarations), `EveryNode` (universal quantification, key, value, domain, body), `WithNode` (target, value), `CallNode` (function name, arguments). The parser validates rule safety: every variable in a rule body must be bound by at least one positive (non-negated) expression. Rules with unsafe variables are rejected with a diagnostic error.

- **Type Checker** (`FizzRegoTypeChecker`): Walks the AST and infers types for all expressions. The type system includes: `BooleanType`, `NumberType` (integer or float), `StringType`, `NullType`, `SetType(element_type)`, `ArrayType(element_type)`, `ObjectType(key_type, value_type)`, `AnyType` (top type for unresolved types), and `UndefinedType` (bottom type for expressions that can never produce a value). Type checking enforces:
  - Comparison operands must be compatible (no comparing numbers to strings)
  - Arithmetic operands must be numeric
  - Set/array/object comprehensions must produce homogeneous collections
  - Function arguments must match the function's signature
  - The `not` keyword can only be applied to boolean-valued expressions
  - `every` domain must be an iterable (set, array, object)

  Type errors are warnings, not hard failures: FizzRego is dynamically typed at runtime, but type warnings flag likely policy authoring errors. The type checker produces an annotated AST with type information on every node.

- **Partial Evaluator** (`FizzRegoPartialEvaluator`): Performs compile-time partial evaluation to optimize policies that reference static data. When data values are known at compile time (loaded from the policy bundle's data document), the partial evaluator:
  - Evaluates constant expressions and folds them into literal values
  - Eliminates dead rule branches where conditions reference static data that makes them trivially true or false
  - Inlines small helper rules (rules with a single body expression) at their call sites
  - Specializes rules that iterate over static collections by unrolling the iteration into concrete rule instances
  - Produces a residual policy: the subset of the original policy that still depends on runtime input. The residual policy is semantically equivalent to the original but faster to evaluate because static decisions have been pre-computed

  Example: if the policy references `data.compliance.regimes` and the bundle's data document contains `{"compliance": {"regimes": ["SOX", "GDPR", "HIPAA"]}}`, a rule that iterates over `data.compliance.regimes` is unrolled into three concrete rules, one per regime, eliminating the runtime iteration.

- **Plan Generator** (`FizzRegoPlanGenerator`): Compiles the (partially evaluated) AST into a linear execution plan -- a sequence of instructions that the evaluation engine executes. Plan instructions include:
  - `SCAN(source, key, value)`: iterate over a collection, binding key and value variables
  - `FILTER(expr)`: evaluate a boolean expression; backtrack if false
  - `LOOKUP(ref)`: resolve a reference in the data or input document
  - `ASSIGN(var, expr)`: bind a variable to a value
  - `CALL(func, args, result)`: invoke a built-in function
  - `NOT(plan)`: negate a sub-plan (succeed if the sub-plan fails)
  - `AGGREGATE(var, plan, result)`: execute a sub-plan, collecting results into a set/array/object
  - `YIELD(value)`: produce a result value
  - `HALT(reason)`: abort evaluation with an error

  The plan is a tree of instructions with backtracking semantics: when a `FILTER` fails, execution backtracks to the most recent `SCAN` and tries the next binding. This is the standard evaluation strategy for datalog-derived languages. The plan generator performs join ordering optimization: when a rule body contains multiple `SCAN` instructions, they are ordered by estimated selectivity (smallest collection first) to minimize the number of intermediate bindings.

### Policy Storage (Bundles)

Versioned, signed collections of policies and data:

- **`PolicyBundle`**: A bundle is the unit of policy distribution. It contains:
  - `manifest.json`: bundle metadata including `revision` (monotonically increasing version), `roots` (list of package path prefixes this bundle governs), `rego_version` (FizzRego language version), `created_at` (timestamp), `author` (who built the bundle)
  - `policies/`: directory of `.rego` files organized by package path (e.g., `fizzbuzz/authz/allow.rego`, `fizzbuzz/compliance/sox.rego`)
  - `data.json`: static data document that policies can reference via `data.*`. Contains role definitions, compliance regime configurations, network policy rules, capability specifications, and any other data that policy rules need but that changes independently of the policy logic
  - `tests/`: directory of test files (`.rego` files containing `test_` prefixed rules) that verify the bundle's policies
  - `.signatures.json`: cryptographic signatures for all bundle files

- **`BundleBuilder`**: Constructs a bundle from a source directory. Resolves `import` statements to verify that all referenced packages exist within the bundle (or are marked as external dependencies). Compiles all policies through the full compiler pipeline (lex → parse → type check → partial evaluate → plan) to catch errors before distribution. Runs all tests in the `tests/` directory. Produces the bundle only if compilation and all tests succeed.

- **`BundleVersionManager`**: Manages bundle versions. Each bundle push increments the revision number. The version manager maintains a history of all bundle revisions with their manifests and activation timestamps. Bundles can be rolled back to any previous revision. The active bundle is the most recently activated revision.

- **`BundleStore`**: Persistent storage for policy bundles. Bundles are stored as compressed archives (tar.gz) in the platform's filesystem persistence backend. The store supports CRUD operations on bundles by name and revision. Content-addressable deduplication: if two bundle revisions share identical policy files, the shared files are stored once with references from both manifests.

- **`BundleSigner`**: Cryptographic signing for bundle integrity and provenance:
  - **Signing**: When a bundle is built, the signer computes SHA-256 hashes of every file in the bundle and signs the hash manifest with an HMAC-SHA256 key (using the same HMAC infrastructure as the auth module). The signatures are stored in `.signatures.json` with the format: `{"files": [{"name": "policies/authz/allow.rego", "hash": "sha256:abc...", "algorithm": "SHA-256"}], "signatures": [{"keyid": "fizzbuzz-policy-signing-key", "sig": "hmac-sha256:def...", "algorithm": "HMAC-SHA256"}]}`
  - **Verification**: When a bundle is loaded, the signer verifies all file hashes against the manifest and verifies the manifest signature against the signing key. If any file has been tampered with or the signature is invalid, the bundle is rejected with a `PolicyBundleIntegrityError`. This prevents unauthorized policy modifications from being activated.

### Decision Logging

Comprehensive audit trail of every policy decision:

- **`DecisionLog`**: Every policy evaluation produces a decision log entry containing:
  - `decision_id`: UUID for the decision
  - `timestamp`: when the decision was made (UTC, nanosecond precision)
  - `path`: the policy rule that was queried (e.g., `data.fizzbuzz.authz.allow`)
  - `input`: the complete input document (the request context)
  - `result`: the policy decision (the value computed by the queried rule)
  - `bundles`: the active bundle revisions at the time of the decision
  - `metrics`: evaluation performance metrics (compilation time, evaluation time, number of rules evaluated, number of backtracks)
  - `labels`: configurable key-value labels for categorization (e.g., `{"enforcement_point": "rbac", "subsystem": "auth"}`)
  - `explanation`: a human-readable trace of which rules fired and why (see Explanation Engine below)

- **`DecisionLogger`**: Collects decision log entries and writes them to the event sourcing journal. The logger supports configurable filtering: only log decisions for specified paths (e.g., only authorization decisions, not health checks), only log denied decisions, or log all decisions. The logger also supports configurable input masking: sensitive fields in the input document (e.g., HMAC tokens, secrets vault entries) are replaced with `[REDACTED]` before logging to prevent credential leakage into the audit trail.

- **`DecisionLogQuery`**: Queries the decision log history. Supports filtering by time range, decision path, result value (allowed/denied), input field values (e.g., "all decisions for user bob"), and bundle revision. Returns paginated results with configurable page size. Used for compliance auditing: "show all authorization decisions in the last 24 hours where the result was deny" or "show all compliance decisions for regime HIPAA since the last bundle update."

- **`DecisionLogExporter`**: Exports decision logs in structured formats for external analysis. Supported formats: JSON Lines (one JSON object per line), CSV (flattened fields), and a format compatible with the FizzSheet spreadsheet engine for compliance reporting. The exporter supports scheduled exports: configure an export schedule (e.g., "export all HIPAA decisions daily at midnight") that writes to the filesystem persistence backend.

### Explanation Engine

Human-readable decision explanations for audit and debugging:

- **`ExplanationEngine`**: Traces the evaluation of a policy query and produces a structured explanation of why the decision was reached. The explanation is a tree of evaluation steps:
  - **`EvalStep`**: a single evaluation step containing the expression being evaluated, its result (true/false/value), the variable bindings at that point, and child steps (for nested evaluations like function calls or sub-queries)
  - **Full trace**: records every expression evaluation, every variable binding, every backtrack, and every rule that was considered. Useful for debugging complex policies but verbose for production use
  - **Summary trace**: records only the rules that contributed to the final decision (the successful proof path) and the first failing condition in rules that did not contribute. Suitable for audit logs and operator diagnostics
  - **Minimal trace**: records only the final decision and the top-level rules that fired. Suitable for high-throughput decision logging where explanation overhead must be minimized

- **`ExplanationFormatter`**: Renders explanations in multiple formats:
  - **Text**: indented text showing the evaluation tree with pass/fail markers:
    ```
    data.fizzbuzz.authz.allow = true
      ├─ [PASS] input.role == "FIZZBUZZ_OPERATOR"
      ├─ [PASS] input.action == "evaluate"
      ├─ [PASS] not suspended[input.user]
      │   └─ [FAIL] suspended["bob"] (no matching entries in data.suspension_list)
      └─ [PASS] not cognitive_overload
          └─ [FAIL] cognitive_overload (data.operator.bob.cognitive_load = 45, threshold 70)
    ```
  - **JSON**: structured JSON representation for programmatic consumption
  - **Decision Graph**: a directed acyclic graph of rule dependencies, showing which rules called which other rules and the data flow between them. Rendered as ASCII art using box-drawing characters

### Data Integration

Pull external data into the policy evaluation context:

- **`DataAdapter`**: An abstract interface for pulling data from platform subsystems into the policy engine's data document. Each adapter maps a platform subsystem's state into a JSON-compatible data structure that policies can reference via `data.*`. Adapters are registered with the policy engine and their data is refreshed at configurable intervals.

- **Built-in Adapters**:
  - **`RBACDataAdapter`**: Pulls role definitions, permission mappings, and user-role bindings from the RBAC module (`auth.py`). Maps to `data.rbac.roles`, `data.rbac.permissions`, `data.rbac.bindings`. Policies can reference `data.rbac.roles[input.user]` to check a user's role.
  - **`ComplianceDataAdapter`**: Pulls compliance regime configurations, clearance records, and audit status from the compliance module (`compliance.py`). Maps to `data.compliance.regimes`, `data.compliance.clearances`, `data.compliance.audit_status`. Policies can check `data.compliance.clearances[input.user]["HIPAA"]` for clearance verification.
  - **`CapabilityDataAdapter`**: Pulls active capability tokens, delegation graphs, and revocation lists from the capability security module (`capability_security.py`). Maps to `data.capabilities.active`, `data.capabilities.delegations`, `data.capabilities.revoked`. Policies can check `not data.capabilities.revoked[input.token_id]`.
  - **`NetworkDataAdapter`**: Pulls network topology, container-to-network mappings, and existing network policy rules from the CNI module (`fizzcni.py`). Maps to `data.network.topology`, `data.network.memberships`, `data.network.policies`. Policies can evaluate network access based on container identity and network membership.
  - **`OperatorDataAdapter`**: Pulls Bob McFizzington's cognitive load metrics, availability status, and approval queue from the operator modules (`fizzbob.py`, `approval.py`, `pager.py`). Maps to `data.operator.bob.cognitive_load`, `data.operator.bob.available`, `data.operator.bob.pending_approvals`. Policies can gate operations on operator state.
  - **`CgroupDataAdapter`**: Pulls container resource utilization from the cgroup module (`fizzcgroup.py`). Maps to `data.containers.resources`. Policies can enforce resource-aware admission control: deny new containers when cluster memory utilization exceeds a threshold.
  - **`DeploymentDataAdapter`**: Pulls deployment status, revision history, and pipeline state from the deployment module (`fizzdeploy.py`). Maps to `data.deployments.status`, `data.deployments.revisions`. Policies can enforce deployment gates: deny new deployments during an active incident or when the previous deployment is still rolling out.

- **`DataRefreshScheduler`**: Manages the refresh cycle for all registered data adapters. Each adapter has a configurable refresh interval (default: 30 seconds for fast-changing data like cognitive load, 5 minutes for slow-changing data like role bindings). The scheduler runs refresh cycles in the background, updating the policy engine's data document atomically (copy-on-write: the new data document replaces the old one in a single pointer swap, ensuring evaluations never see partially updated data). Stale data warnings are emitted when an adapter's refresh fails and the data age exceeds twice the refresh interval.

### Built-in Functions

A library of built-in functions available in FizzRego policies:

- **String Functions**:
  - `concat(delimiter, array)`: join array elements with a delimiter
  - `contains(string, search)`: check if string contains search
  - `endswith(string, suffix)`: check if string ends with suffix
  - `format_int(number, base)`: format integer in the specified base
  - `indexof(string, search)`: find first index of search in string
  - `lower(string)`: convert to lowercase
  - `replace(string, old, new)`: replace all occurrences
  - `split(string, delimiter)`: split string into array
  - `sprintf(format, values)`: formatted string construction
  - `startswith(string, prefix)`: check if string starts with prefix
  - `substring(string, start, length)`: extract substring
  - `trim(string, cutset)`: trim characters from both ends
  - `trim_left(string, cutset)`: trim from left
  - `trim_right(string, cutset)`: trim from right
  - `trim_prefix(string, prefix)`: remove prefix
  - `trim_suffix(string, suffix)`: remove suffix
  - `trim_space(string)`: trim whitespace
  - `upper(string)`: convert to uppercase
  - `strings.reverse(string)`: reverse a string

- **Regex Functions**:
  - `regex.match(pattern, value)`: check if value matches regex pattern
  - `regex.find_all_string_submatch(pattern, value, count)`: find all submatches
  - `regex.replace(string, pattern, replacement)`: regex replacement
  - `regex.split(pattern, string)`: split on regex pattern
  - `regex.is_valid(pattern)`: check if pattern is a valid regex

  Regex functions delegate to the FizzRegex engine (`regex_engine.py`) for evaluation, using the platform's own regular expression implementation rather than Python's `re` module. This ensures consistent regex semantics across the entire platform.

- **Aggregation Functions**:
  - `count(collection)`: number of elements in a set, array, or object
  - `sum(array)`: sum of numeric array elements
  - `product(array)`: product of numeric array elements
  - `max(collection)`: maximum value
  - `min(collection)`: minimum value
  - `sort(array)`: sort array in ascending order

- **Type Functions**:
  - `type_name(value)`: return the type name as a string ("boolean", "number", "string", "null", "set", "array", "object")
  - `is_boolean(value)`, `is_number(value)`, `is_string(value)`, `is_null(value)`, `is_set(value)`, `is_array(value)`, `is_object(value)`: type predicates
  - `to_number(value)`: convert string to number

- **Object Functions**:
  - `object.get(object, key, default)`: get value with default
  - `object.remove(object, keys)`: remove keys from object
  - `object.union(objects)`: merge multiple objects (last wins)
  - `object.filter(object, keys)`: keep only specified keys
  - `object.keys(object)`: get keys as a set
  - `object.values(object)`: get values as an array

- **Set Functions**:
  - `intersection(sets)`: intersection of multiple sets
  - `union(sets)`: union of multiple sets
  - `set.diff(a, b)`: elements in a but not in b

- **Encoding Functions**:
  - `json.marshal(value)`: serialize value to JSON string
  - `json.unmarshal(string)`: parse JSON string to value
  - `base64.encode(string)`: Base64 encode
  - `base64.decode(string)`: Base64 decode
  - `urlquery.encode(string)`: URL query encode
  - `urlquery.decode(string)`: URL query decode
  - `yaml.marshal(value)`: serialize value to YAML string
  - `yaml.unmarshal(string)`: parse YAML string to value

- **Time Functions**:
  - `time.now_ns()`: current time in nanoseconds since epoch
  - `time.parse_ns(layout, value)`: parse time string to nanoseconds
  - `time.format(ns, layout)`: format nanoseconds as time string
  - `time.date(ns)`: extract [year, month, day] from nanoseconds
  - `time.clock(ns)`: extract [hour, minute, second] from nanoseconds
  - `time.weekday(ns)`: day of week (0=Sunday)
  - `time.add_date(ns, years, months, days)`: date arithmetic
  - `time.diff(ns1, ns2)`: compute [years, months, days, hours, minutes, seconds] between two times

- **Net Functions**:
  - `net.cidr_contains(cidr, addr)`: check if IP address is within CIDR range
  - `net.cidr_intersect(cidr1, cidr2)`: check if two CIDR ranges overlap
  - `net.cidr_merge(cidrs)`: merge adjacent CIDR ranges
  - `net.cidr_expand(cidr)`: expand CIDR to list of individual addresses

  Net functions integrate with the FizzCNI module's IPAM subsystem for consistent IP address handling.

- **JWT Functions** (integration with the auth module's HMAC infrastructure):
  - `io.jwt.decode(token)`: decode a JWT/HMAC token without verification, returning [header, payload, signature]
  - `io.jwt.verify_hmac_sha256(token, secret)`: verify an HMAC-SHA256 signed token
  - `io.jwt.decode_verify(token, constraints)`: decode and verify in one step, checking signature, expiration, issuer, audience, and other claims against the constraints object

- **Crypto Functions**:
  - `crypto.sha256(string)`: SHA-256 hash
  - `crypto.hmac_sha256(key, message)`: HMAC-SHA256
  - `crypto.md5(string)`: MD5 hash (for non-security purposes like cache keys)

- **FizzBuzz Domain Functions** (platform-specific built-ins not found in standard OPA):
  - `fizzbuzz.evaluate(number)`: evaluate a number through the core FizzBuzz engine, returning the result string. Enables policies that gate actions based on the FizzBuzz classification of a number
  - `fizzbuzz.is_fizz(number)`: check if a number is classified as Fizz (n % 3 == 0)
  - `fizzbuzz.is_buzz(number)`: check if a number is classified as Buzz (n % 5 == 0)
  - `fizzbuzz.is_fizzbuzz(number)`: check if a number is classified as FizzBuzz (n % 15 == 0)
  - `fizzbuzz.cognitive_load()`: return Bob McFizzington's current NASA-TLX cognitive load score. Enables policies that adapt based on operator state without requiring the operator data adapter

### Evaluation Engine

The core runtime that evaluates policy queries:

- **`PolicyEngine`**: The central evaluation entry point. Receives a query (a reference path like `data.fizzbuzz.authz.allow`), an input document (the request context), and returns a decision. The engine:
  1. Resolves the query path to the compiled plan for the target rule
  2. Constructs the evaluation context: input document from the caller, data document from the data adapters, and the compiled rule plans from the active policy bundle
  3. Executes the plan using the `PlanExecutor`
  4. Records the decision in the decision log
  5. Returns the result with optional explanation

- **`PlanExecutor`**: Executes compiled plan instructions with backtracking. Maintains an execution stack of variable bindings. When a `FILTER` instruction fails, the executor pops the stack to the most recent `SCAN` choice point and tries the next binding. The executor enforces configurable limits:
  - **Evaluation timeout**: maximum wall-clock time for a single evaluation (default: 100ms). Prevents runaway evaluations from blocking request processing
  - **Max iterations**: maximum number of plan instruction executions (default: 100,000). Prevents infinite loops from policies that inadvertently create unbounded iteration
  - **Max output size**: maximum size of the result document in bytes (default: 1MB). Prevents policies from generating excessively large result sets

- **`EvaluationCache`**: Caches the results of policy evaluations for identical (query, input, data_version) tuples. The cache uses LRU eviction with a configurable maximum size (default: 10,000 entries). Cache entries are invalidated when the active bundle revision changes or when any data adapter refreshes its data. The cache key is computed as the SHA-256 hash of the query path, the JSON-serialized input, and the data version counter. Cache hit rates are reported as metrics. The MESI cache coherence protocol from the platform's existing cache module (`cache.py`) is used for cache state management, ensuring that concurrent evaluations do not serve stale decisions.

- **`EvaluationMetrics`**: Collects per-evaluation performance metrics:
  - `eval_duration_ns`: total evaluation time in nanoseconds
  - `compile_duration_ns`: time spent compiling (if the policy was not pre-compiled)
  - `plan_instructions_executed`: number of plan instructions executed
  - `backtracks`: number of backtracking events
  - `cache_hit`: whether the result was served from cache
  - `rules_evaluated`: number of rule bodies evaluated
  - `data_lookups`: number of data document lookups
  - `builtin_calls`: number of built-in function invocations

  Metrics are reported to FizzOTel for tracing and to FizzSLI for service level monitoring.

### Policy Testing Framework

First-class testing support for policies:

- **Test Rules**: Rules prefixed with `test_` in `.rego` files are automatically recognized as tests:
  ```
  test_admin_allowed {
      allow with input as {
          "role": "FIZZBUZZ_SUPERUSER",
          "action": "evaluate",
          "number": 42,
          "user": "bob",
      }
  }

  test_anonymous_denied {
      not allow with input as {
          "role": "ANONYMOUS",
          "action": "evaluate",
          "number": 42,
          "user": "guest",
      }
  }

  test_suspended_user_denied {
      not allow with input as {
          "role": "FIZZBUZZ_OPERATOR",
          "action": "evaluate",
          "number": 42,
          "user": "alice",
      } with data.suspension_list as [
          {"user": "alice", "expires_at": 9999999999999999999},
      ]
  }

  test_sox_segregation {
      violation := compliance_violations with input as {
          "user": "bob",
          "action": "evaluate_and_approve",
      } with data.compliance.cleared as {}
      count(violation) == 3
  }
  ```

- **`PolicyTestRunner`**: Discovers and executes all `test_` rules in a bundle's `tests/` directory. Each test is an independent evaluation: `with` overrides are scoped to the test rule and do not affect other tests. The runner reports:
  - Total tests, passed, failed, errored
  - Per-test execution time
  - For failed tests: the expected result, the actual result, and the explanation trace showing which condition diverged from expectation
  - Coverage: which rules in the policy were exercised by the test suite and which were not

- **`PolicyCoverageAnalyzer`**: Instruments policy evaluation to track which rules, expressions, and data paths are exercised during test execution. Reports:
  - **Rule coverage**: percentage of rules that were evaluated at least once
  - **Expression coverage**: percentage of rule body expressions that were evaluated to true at least once AND to false at least once (branch coverage)
  - **Data coverage**: which keys in the data document were accessed during test execution
  - Coverage is reported per-file and per-package, with an overall coverage percentage. The `BundleBuilder` can enforce a minimum coverage threshold (default: 80%) -- bundles with insufficient test coverage are rejected.

- **`PolicyBenchmark`**: Benchmarks policy evaluation performance. Runs a specified query with specified input N times (default: 1000) and reports: mean evaluation time, p50, p95, p99, min, max, allocations per evaluation, and cache effect (with cache vs. without cache). Used to detect performance regressions when policies are updated. The `BundleBuilder` can enforce a maximum evaluation time threshold (default: 10ms p99) -- bundles with policies that exceed the threshold are flagged with performance warnings.

### Real-Time Policy Updates

Live policy reloading without service restart:

- **`PolicyWatcher`**: Monitors the bundle store for new bundle activations. When a new bundle revision is activated (via `BundleVersionManager.activate(revision)`), the watcher:
  1. Loads the new bundle from the `BundleStore`
  2. Verifies the bundle signature via `BundleSigner`
  3. Compiles all policies through the full compiler pipeline
  4. Runs all bundle tests via `PolicyTestRunner`
  5. If compilation and tests succeed: atomically swaps the active policy engine's compiled plans to the new bundle's plans. In-flight evaluations complete against the old plans; new evaluations use the new plans. The swap is a single pointer assignment, so there is no window where evaluations fail.
  6. If compilation or tests fail: rejects the new bundle, logs the failure, alerts via FizzPager, and retains the current active bundle. The platform never serves decisions from a bundle that failed compilation or testing.
  7. Invalidates the evaluation cache (all entries become stale since the policy changed)

- **`PolicyHotReloadMiddleware`**: Integrates with the platform's hot-reload system (Raft consensus from the infrastructure module). When the platform runs in a multi-node configuration, a bundle activation on the leader node is replicated to follower nodes via the Raft log. Each follower's `PolicyWatcher` receives the activation event and performs the same load-verify-compile-test-swap cycle, ensuring all nodes converge to the same policy version. This is consistent with the platform's existing Raft-based hot-reload pattern.

### Integration Points

How FizzPolicy connects to existing platform subsystems:

- **Authorization Integration** (`auth.py`): The RBAC module's `AuthorizationMiddleware` delegates its permission check to FizzPolicy. Instead of evaluating hardcoded role-permission mappings, the middleware constructs an input document containing `{role, action, number, user, token}` and queries `data.fizzbuzz.authz.allow`. The RBAC module retains its role definitions, token validation, and access denied response builder. Only the decision logic moves to FizzRego.

- **Compliance Integration** (`compliance.py`): The `ComplianceMiddleware` delegates its regime-specific checks to FizzPolicy. SOX segregation rules, GDPR consent requirements, and HIPAA minimum necessary levels are expressed as FizzRego policies. The compliance module retains its data models, audit logging, and erasure paradox handling. The decision "is this action compliant under SOX/GDPR/HIPAA?" moves to `data.fizzbuzz.compliance.approved`.

- **Capability Security Integration** (`capability_security.py`): The `CapabilityMiddleware` uses FizzPolicy to evaluate whether a capability token authorizes a requested operation. The capability module retains the CapabilityMint, the delegation graph, and the revocation cascade. The decision "does this token grant this operation on this resource?" moves to `data.fizzbuzz.capabilities.authorized`.

- **Network Policy Integration** (`fizzcni.py`): The `NetworkPolicyEngine` delegates ingress/egress decisions to FizzPolicy. Network policy rules are expressed as FizzRego policies operating on source/destination container identities, port numbers, and protocol types. The CNI module retains packet-level enforcement. The decision logic moves to `data.fizzbuzz.network.permitted`.

- **Admission Control Integration**: A new `AdmissionController` component that intercepts all resource creation requests (container creation, deployment creation, configuration changes, secret access) and evaluates them against FizzPolicy. The admission controller acts as a universal policy enforcement point, querying `data.fizzbuzz.admission.allowed` before any resource mutation proceeds. This is the FizzBuzz equivalent of Kubernetes admission webhooks.

- **API Gateway Integration**: The reverse proxy module (`fizzproxy.py`) integrates FizzPolicy as a request-level policy enforcement point. Incoming API requests are evaluated against `data.fizzbuzz.gateway.allowed` before being proxied to backend services. Policies can enforce rate limits, IP allowlists, request body validation, and authentication requirements at the gateway level.

- **Service Mesh Integration**: The service mesh data plane integrates FizzPolicy for inter-service authorization. When one service makes a request to another, the mesh sidecar evaluates `data.fizzbuzz.mesh.allowed` with the source service identity, destination service identity, and request metadata. This implements service-to-service mTLS authorization policies without application code changes.

- **Deployment Gate Integration**: The deployment pipeline (`fizzdeploy.py`) evaluates `data.fizzbuzz.deploy.allowed` before executing each pipeline stage. Policies can enforce deployment windows (no deployments between 2am and 6am), change freeze periods (no deployments during the mobile release cut), required approvals (production deployments require FizzApproval sign-off), and incident awareness (no deployments during active P1 incidents).

### Default Policy Bundle

A comprehensive default policy bundle shipped with the platform:

- **`fizzbuzz/authz/`**: Authorization policies migrated from the RBAC module:
  - `allow.rego`: Role-based evaluation permissions (SUPERUSER: full access, OPERATOR: evaluate and configure, ANALYST: read-only, VIEWER: limited range, ANONYMOUS: demo range 1-10)
  - `range.rego`: Maximum evaluation range per role
  - `tokens.rego`: Token validity and expiration checks

- **`fizzbuzz/compliance/`**: Compliance policies migrated from the compliance module:
  - `sox.rego`: Segregation of duties (evaluator != approver, duty partitioning per role)
  - `gdpr.rego`: Consent requirements (data subject consent before evaluation, right-to-erasure handling)
  - `hipaa.rego`: Minimum necessary (access level checks, PHI encryption requirements)
  - `cross_regime.rego`: Cross-regime conflict resolution (when SOX and GDPR requirements conflict, which takes precedence)

- **`fizzbuzz/capabilities/`**: Capability policies migrated from the capability security module:
  - `authorize.rego`: Capability token validation and operation authorization
  - `delegation.rego`: Delegation chain validation (no amplification, revocation checks)
  - `attenuation.rego`: Attenuation rules (narrowing is allowed, broadening is not)

- **`fizzbuzz/network/`**: Network policies migrated from the CNI module:
  - `ingress.rego`: Inbound traffic rules per service
  - `egress.rego`: Outbound traffic rules per service
  - `isolation.rego`: Network segment isolation (security services cannot be reached from exotic services)

- **`fizzbuzz/admission/`**: New admission control policies:
  - `containers.rego`: Container creation admission (resource limits must be set, non-root user required, approved images only)
  - `deployments.rego`: Deployment admission (change freeze enforcement, approval requirements, cognitive load gating)
  - `secrets.rego`: Secret access admission (only services with declared secret dependencies can access vault entries)
  - `config.rego`: Configuration change admission (configuration changes to production require FizzApproval sign-off)

- **`fizzbuzz/gateway/`**: API gateway policies:
  - `ratelimit.rego`: Rate limiting per client, per role, and per endpoint
  - `request.rego`: Request validation (required headers, body size limits, content type enforcement)

- **`fizzbuzz/mesh/`**: Service mesh policies:
  - `mtls.rego`: mTLS authorization (which services can communicate with which services)
  - `circuit.rego`: Circuit breaker thresholds per service pair

- **`fizzbuzz/deploy/`**: Deployment gate policies:
  - `windows.rego`: Deployment window enforcement (allowed hours, blocked dates)
  - `freeze.rego`: Change freeze periods
  - `gates.rego`: Required pre-deployment gates (approval, test pass, scan pass)

- **`data.json`**: Default data document containing role definitions, compliance regime configurations, network topology, deployment windows, rate limits, and other policy-relevant data. All values are overridable via the `ConfigurationManager` and CLI flags.

### FizzPolicy Middleware

`FizzPolicyMiddleware` integrates with the platform's middleware pipeline. It intercepts every FizzBuzz evaluation request and evaluates the platform's unified admission policy: `data.fizzbuzz.admission.allowed`. The middleware constructs the input document from the `ProcessingContext` (user, role, number, action, token, compliance clearances, capabilities, source container, target service) and passes it to the `PolicyEngine`. If the policy denies the request, the middleware short-circuits the pipeline and returns a structured denial response including the explanation trace. If the policy allows the request, evaluation proceeds through the remaining middleware. The middleware records evaluation metrics (policy evaluation latency, cache hit rate, decision distribution) for FizzSLI monitoring.

### CLI Integration

- `--fizzpolicy`: Enable the FizzPolicy declarative policy engine
- `--fizzpolicy-bundle <path>`: Load a policy bundle from the specified path
- `--fizzpolicy-bundle-build <source_dir>`: Build a policy bundle from a source directory (compile, test, sign)
- `--fizzpolicy-bundle-push <path>`: Push a built bundle to the bundle store
- `--fizzpolicy-bundle-activate <revision>`: Activate a specific bundle revision
- `--fizzpolicy-bundle-rollback <revision>`: Rollback to a previous bundle revision
- `--fizzpolicy-bundle-list`: List all bundle revisions with metadata
- `--fizzpolicy-eval <query> --fizzpolicy-input <json>`: Evaluate a policy query with the given input (command-line policy testing)
- `--fizzpolicy-eval-explain <query> --fizzpolicy-input <json>`: Evaluate with full explanation trace
- `--fizzpolicy-test <bundle_path>`: Run all tests in a policy bundle
- `--fizzpolicy-test-coverage <bundle_path>`: Run tests with coverage analysis
- `--fizzpolicy-bench <query> --fizzpolicy-input <json>`: Benchmark a policy query
- `--fizzpolicy-decisions`: Query the decision log (supports `--since`, `--until`, `--path`, `--result`, `--user` filters)
- `--fizzpolicy-decisions-export <format>`: Export decision logs (json, csv, fizzsheet)
- `--fizzpolicy-data-refresh`: Trigger an immediate refresh of all data adapters
- `--fizzpolicy-status`: Show policy engine status (active bundle revision, data adapter health, cache hit rate, evaluation latency p50/p95/p99)
- `--fizzpolicy-compile <file.rego>`: Compile a single FizzRego file and show diagnostics (type warnings, safety errors)

---

## Why This Is Necessary

Because the Enterprise FizzBuzz Platform's access control posture is an archaeological artifact. Five independent subsystems enforce five overlapping sets of constraints using five different evaluation engines, five different data models, and five different audit formats. When the compliance team asks "what are all the conditions under which a FIZZBUZZ_ANALYST can evaluate numbers above 100?" the answer requires reading Python code across three modules (auth, compliance, capability_security), understanding each module's internal branching logic, and mentally composing the results -- because no system can answer the question holistically. When a policy change is required -- say, "during a change freeze, deny all deployments except emergency patches approved by Bob" -- the engineer must determine which subsystems are involved (deployment, approval, operator cognitive load, RBAC), modify procedural code in each, write tests in each, and deploy all changes simultaneously. A declarative policy engine reduces this to a three-line FizzRego rule.

Policy-as-code is the industry-standard approach for the same reason infrastructure-as-code displaced manual server configuration. Imperative policy enforcement (if/else chains in application code) does not compose, does not audit, does not version, and does not scale. Declarative policy (data-driven rules evaluated by a general-purpose engine) does all four. OPA is deployed in production at organizations ranging from Netflix to the US Department of Defense. The pattern is proven. The Enterprise FizzBuzz Platform's compliance requirements (SOX, GDPR, HIPAA) make a unified, auditable, declarative policy layer not just beneficial but operationally essential. A single policy evaluation that crosses all compliance regimes, produces a decision log entry, and explains its reasoning in human-readable format is the difference between "we think we're compliant" and "we can prove it -- here is the decision log, here are the policies, here are the tests, here is the coverage report."

The platform has 116 infrastructure modules. Every one of them makes authorization decisions. Today, each module makes those decisions in its own way. FizzPolicy gives them one way. One language. One compiler. One engine. One audit trail. One testing framework. One management interface. The policies are readable. The decisions are explainable. The bundles are signed. The changes are versioned. The platform's access control posture stops being implicit in code and becomes explicit in policy.

---

## Estimated Scale

~3,500 lines of policy engine implementation, ~450 lines of FizzRego language implementation (lexer: ~200 lines for tokenization with 30+ token types, string escapes, number literals, and diagnostic source locations; parser: ~250 lines for recursive descent with precedence climbing, AST node construction, and safety validation), ~400 lines of type checker (type inference, compatibility checks, warning generation, annotated AST production), ~350 lines of partial evaluator (constant folding, dead branch elimination, rule inlining, iteration unrolling, residual policy generation), ~300 lines of plan generator (instruction emission, backtracking structure, join ordering, selectivity estimation), ~350 lines of policy bundle system (BundleBuilder, BundleVersionManager, BundleStore, content-addressable deduplication, compressed archive format), ~200 lines of bundle signing (SHA-256 hashing, HMAC-SHA256 signing, verification, integrity checking), ~350 lines of decision logging (DecisionLog, DecisionLogger, DecisionLogQuery, DecisionLogExporter, input masking, scheduled exports), ~250 lines of explanation engine (EvalStep tree construction, full/summary/minimal trace modes, text/JSON/graph formatters), ~300 lines of data integration (DataAdapter interface, 7 built-in adapters, DataRefreshScheduler, atomic data swap, stale data warnings), ~350 lines of built-in functions (string: 18 functions, regex: 5 functions, aggregation: 6 functions, type: 9 functions, object: 5 functions, set: 3 functions, encoding: 8 functions, time: 8 functions, net: 4 functions, JWT: 3 functions, crypto: 3 functions, FizzBuzz domain: 4 functions), ~400 lines of evaluation engine (PolicyEngine, PlanExecutor, EvaluationCache with MESI coherence, EvaluationMetrics, timeout/iteration/output limits), ~250 lines of policy testing framework (PolicyTestRunner, PolicyCoverageAnalyzer, PolicyBenchmark, coverage thresholds, performance thresholds), ~150 lines of real-time policy updates (PolicyWatcher, PolicyHotReloadMiddleware, Raft integration, atomic plan swap, cache invalidation), ~250 lines of integration points (authorization, compliance, capability, network, admission, gateway, mesh, deployment gate integrations), ~200 lines of default policy bundle (8 policy packages, 20+ .rego files, data.json), ~200 lines of middleware and CLI integration, ~500 tests. Total: ~5,700 lines.

---
