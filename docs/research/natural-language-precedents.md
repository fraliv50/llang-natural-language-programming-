# Natural-Language Programming Precedents: What to Steal, What to Avoid

> **Research note** for the design of a new programming language that reads like structured natural language, whose primary author *and* reader is an LLM rather than a human.
>
> Date: 2026-11-22. Method: live web search and page fetches (links inline). Where I rely on community anecdotes rather than primary documentation, I say so. Nothing in this document is a claim about *your* language yet — it is a survey of prior art and the lessons I would carry forward.

---

## Executive summary

1. **"English-like" has succeeded exactly twice, for the same reason:** the domain was tiny and the nouns were visible on screen. HyperTalk succeeded because a button, card, and field were right there in the UI; SQL succeeded because a table, column, and row were the only nouns that existed. Neither language tried to parse English generally.
2. **Every attempt to add grammatical *variety* to make code feel more natural backfired.** AppleScript's own designers concluded the experiment "was not successful" and that "the syntactic variations and flexibility did more to confuse programmers than to help them out." Inform 7 users report never being sure whether a line was even valid.
3. **Verbosity is not the problem; unbound vocabulary is.** COBOL's 300+ reserved words and four-division hierarchy made programs self-documenting *and* eventually "incomprehensible." Fixed structure was the good part; the sprawling vocabulary and hidden defaults were the bad part.
4. **The strongest positive pattern is Gherkin's:** a *closed* set of structural keywords (`Feature`, `Scenario`, `Given`, `When`, `Then`, `And`) plus free-form text in slots, with every sentence bound to a deterministic implementation. Structured scaffold, natural-language payload, explicit binding.
5. **For an LLM reader, terse syntax is pure downside.** A model pays no human cost for extra tokens, but pays heavily for ambiguity, sparse grammar, and lack of redundancy. Human-optimized compactness removes exactly the signal a model uses to disambiguate.
6. **The 2024–2026 LLM-era work converges on a single architecture:** a small constrained language + a compiler/validator + error feedback into the model + (optionally) grammar-constrained decoding. The DSL becomes the durable, diffable artifact; the LLM is a generator and a natural-language front end, *not* the interpreter of record.

---

## Cross-cutting comparison

| Language | How natural is it, really? | What was pleasant | Main failure mode | Lesson for us |
|---|---|---|---|---|
| COBOL (1959) | English-like keywords and sentence structure; heavily stylized, not English | Self-documenting; managers could skim it | 300+ reserved words, rigid boilerplate, "incomprehensible" legacy code | Fixed macro-structure is good; unbounded vocabulary and hidden defaults are bad |
| SQL / SEQUEL (1973) | Keyword-delimited clauses, not prose; declarative | Clause keywords are explicit delimiters; says *what*, not *how* | Dialect fragmentation, `NULL` three-valued logic, non-relational escapes | Declarative + strongly delimited is a great LLM target; standardize one dialect |
| HyperTalk (1987) | Genuinely sentence-like ("put the first word of the third line of field X into...") | Reads like English; direct manipulation of visible objects | Contextual name resolution (`me`, `target`), message-hierarchy magic, slow, untyped | Natural language works in a closed world with visible nouns; avoid contextual resolution |
| AppleScript (1993) | Multi-token keywords, "natural language metaphor" | Reads well *when already correct* | Designers called it a failure; trial-and-error syntax; per-app dictionaries; reserved words as variable names | Never let application vocabularies redefine the language; never let "reads well" substitute for "writable" |
| Inform 7 (2006) | Closest to real English prose; full NLP-style parser | Excellent for *reading*; literate, literary | Users cannot tell if a line is valid; syntactic sugar hides how code works; must memorize arbitrary prepositions | Use one canonical phrasing per construct; expose structure rather than hiding it |
| Gherkin (2008+) | Restricted English sentence frames | Tiny closed vocabulary; readable by non-programmers; binds to code | Ambiguous step definitions; keywords ignored during matching; NL ambiguity | **Best template:** closed structural keywords + NL slots + explicit binding + duplicate detection |
| NL-programming research (1960s–today) | Actual natural language | Expressive; accessible | Ambiguity, domain dependence, ALPAC-style overpromising | Ask for clarification rather than guessing; constrain the world model |
| LLM-era DSLs (2023–2026) | Pseudocode / structured NL interpreted by a model | Fast authoring; LLM can translate loose intent into a small formal core | Models still confabulate; "valid is not correct"; nondeterminism | Small grammar + validator + feedback loop + constrained decoding; LLM is front end, not runtime |

---

## 1. COBOL (1959)

**Syntax approach.** English-like statements built from verbs, nouns, and clauses: `MOVE x TO y`, `IF ... THEN ... ELSE ...`, `PERFORM paragraph`. A program is split into four rigid divisions — IDENTIFICATION, ENVIRONMENT, DATA, PROCEDURE — with a hierarchy of sections, paragraphs, sentences, and statements. It is prose-shaped, but a highly constrained, stylized prose with 300+ reserved words ([Wikipedia](https://en.wikipedia.org/wiki/COBOL), [IBM](https://www.ibm.com/think/topics/cobol)).

**What made it readable / pleasant.** The explicit goal was self-documentation: "the syntax is kept simple to allow non-programmers ('The Business') to read it and understand it. COBOL is meant to be explicit, because there shouldn't be room for assumptions" (Cigna engineer quoted on [Stack Overflow](https://stackoverflow.blog/2020/04/20/brush-up-your-cobol-why-is-a-60-year-old-language-suddenly-in-demand)). The Data Division's declarative field descriptions are genuinely excellent — a record layout reads like a specification. Divisions give a predictable macro-structure: you always know where to find data definitions and where to find executable logic.

**What failed / was awkward.** Verbosity tipped into unmaintainability: by 1984 maintainers were struggling with "incomprehensible" code, and COBOL-85 was largely a maintenance rescue mission ([Wikipedia](https://en.wikipedia.org/wiki/COBOL)). The huge reserved-word set, fixed-format source in older versions, and heavy boilerplate meant a trivial program needed a lot of scaffolding. The "readable to managers" claim was only ever half-true — managers could skim it, not modify it.

**Transferable lesson.** Separate *declarative structure* (definitions, schemas, "this is what exists") from *imperative logic*, and make each visually unmistakable. Keep a fixed, small set of top-level sections. But do not equate "lots of English words" with readability: every extra reserved word is a potential collision and a thing a writer must remember. COBOL's best idea is the fixed skeleton; its worst is the unbounded vocabulary and implicit defaults.

---

## 2. SQL / SEQUEL (1973)

**Syntax approach.** SEQUEL stood for *Structured English Query Language*; the name was shortened because "SEQUEL" was a trademark ([Wikipedia](https://en.wikipedia.org/wiki/SQL)). The surface is English keywords in a fixed clause order — `SELECT ... FROM ... WHERE ... GROUP BY ... HAVING ... ORDER BY ...` — but it is emphatically **not** prose. It is a declarative language: you describe the result you want, not the procedure to compute it ([IBM](https://www.ibm.com/think/topics/structured-query-language), [dbt Labs](https://www.getdbt.com/blog/a-brief-history-of-sql)).

**What made it readable / pleasant.** Clause keywords are *explicit delimiters*. `WHERE` ends the projection and starts a predicate; there is no punctuation-based nesting to track. The declarative semantics mean a short query expresses a lot: the engine handles joins, indexing, and execution order. Early adopters praised its "stability, predictability, and usability" ([McGovern Foundation](https://www.mcgovern.org/the-legacy-of-patrick-j-mcgovern/from-the-pages-of-tech-history/feb-16-1987-sql-establishes-dominance-in-database-query-language-arena)).

**What failed / was awkward.** Dialect fragmentation (T-SQL, PL/pgSQL, MySQL, etc.) made portability a perpetual chore. `NULL` and three-valued logic surprise people constantly. The language is not fully relational and has accreted procedural extensions. Crucially, the *natural-language* part was the first thing to go: real SQL is keyword-delimited precisely because free-form English was unusable. The long research line on NL-to-SQL exists because humans want to ask questions in English and SQL is too hard for them ([VLDB survey](https://www.vldb.org/pvldb/vol13/p1737-kim.pdf)).

**Transferable lesson.** This is the strongest precedent for our language: **declarative intent + a small closed set of uppercase-ish structural keywords + explicit clause delimiters**. Also: pick one canonical form and resist dialect sprawl. If we need multiple surfaces, make them compile to one IR, not diverge.

---

## 3. HyperTalk (1987)

**Syntax approach.** HyperCard's scripting language, "programming for the rest of us" by Bill Atkinson and Dan Winkler. Genuinely sentence-shaped: `put the first word of the third line of field "hello" into field "goodbye"`; `if ... then ... else ...`; event handlers like `on mouseUp ... end mouseUp`. It is event-driven and message-passing over a fixed object hierarchy (stack → background → card → button/field) ([Grokipedia overview](https://grokipedia.com/page/HyperTalk), [formal grammar appendix](http://www.memoryhole.net/~kyle/newwebsite/Curriculum_Vitae_files/hypertalk.pdf)).

**What made it readable / pleasant.** The vocabulary was *grounded in visible objects*. You weren't writing about abstract variables; you were writing about a button you could see, with a card behind it. Commands mapped to direct-manipulation actions. "Chunk expressions" (`word 2 of line 3 of field X`) let text processing read like an instruction to a person. For a closed domain with a small set of nouns, the English-like grammar was a genuine productivity win — by some estimates 70% of Macintosh owners tried scripting it ([Tricks of the HyperTalk Masters](http://www.jaedworks.com/hypercard/HT-Masters/scripting.html)).

**What failed / was awkward.** Contextual name resolution: `me`, `target`, `the msg box`, and the message hierarchy meant the meaning of a name depended on where the script lived and how the message propagated. That is exactly the kind of implicit context that is fine when you can see the card in front of you and terrible when you cannot. It was untyped, interpreted (later compiled), slow for serious work, and tied to a platform Apple eventually discontinued in 2004.

**Transferable lesson.** Natural-language syntax is most successful when the **domain is closed and the nouns are grounded**. If we adopt that style, names must be explicit and globally resolvable — no `me`, no `target`, no "current context." Never make a construct's meaning depend on dynamic lookup up a hierarchy.

---

## 4. AppleScript (1993)

**Syntax approach.** A "natural language metaphor" for scripting applications, built largely on HyperTalk: multi-token keywords (`tell application "Finder" to ...`), optional prepositions, and per-application dictionaries contributed by each app vendor. It aimed to be readable by anyone and was localized into multiple dialects including English, Japanese, and French ([Wikipedia](https://en.wikipedia.org/wiki/AppleScript), [Apple Language Guide](https://developer.apple.com/library/archive/documentation/AppleScript/Conceptual/AppleScriptLangGuide/introduction/ASLR_intro.html)).

**What made it readable / pleasant.** When a script is already correct, it reads beautifully: `tell application "Mail" to get the subject of the first message of the inbox`. Recording UI actions could generate a starting script. The *reading* experience is the language's one unqualified success.

**What failed / was awkward.** This is the cautionary tale, and unusually, the designers said so themselves. William Cook and others wrote in *AppleScript: A Language for the Rest of Us?*:

> "The experiment in designing a language that resembled natural languages (English and Japanese) was not successful... This led to the invention of multi-token keywords and the ability to disambiguate tokens without spaces for Japanese Kanji. In the end the syntactic variations and flexibility did more to confuse programmers than to help them out." — [UT Austin PDF](https://www.cs.utexas.edu/~wcook/Drafts/2006/ashopl.pdf)

Concrete symptoms:
- **You cannot tell whether a line is valid.** "Mostly due to the English-like syntax, you can almost only code through trial and error. You never really know whether you got the syntax right" ([RedSweater blog](https://redsweater.com/blog/502/apples-script), quoting the paper's author).
- **Reserved words collide with ordinary names.** Naming a variable `yes` produces a bizarre error about a built-in word ([Andy Kong](https://andykong.org/blog/applescripts1)).
- **No standard vocabulary across applications.** Every app developer invents their own terminology and uses it differently, so learning one app's dictionary does not teach you the next ([Automators Talk](https://talk.automators.fm/t/is-it-worth-it-to-learn-applescript-at-this-point-and-time/6834)).
- The planned "pro syntax" (a conventional expression syntax) never shipped.

**Transferable lesson.** Three hard rules: **(1)** exactly one canonical phrasing per construct, no optional prepositions or synonyms; **(2)** reserved keywords must be unambiguously distinguishable from user identifiers (sigil, namespace, or enforced casing); **(3)** never let third-party libraries redefine core syntax or vocabulary. "Reads like English" is not a success criterion — "a writer can predict the correct form without trial and error" is.

---

## 5. Inform 7 (2006)

**Syntax approach.** A natural-language-based language for interactive fiction, drawing on linguistics and literate programming. Programs are written as prose-like rules and assertions:

```inform7
The piano can be either tuned or out of tune. The piano is out of tune.

Tuning is an action applying to one thing.
Check tuning:
    if the noun is out of tune, say "That is already in tune." instead.
Carry out tuning:
    now the noun is tuned.
```

Full stops terminate statements; indentation indicates scope; phrases are the functions. It has relations, rulebooks, "text substitutions" in square brackets inside quoted strings, and a large generated vocabulary ([Inform website](https://ganelson.github.io/inform-website), [Learn Inform 7 in Y Minutes](https://learnxinyminutes.com/inform7), [Inform 7 Concepts](https://catn.decontextualize.com/inform7)).

**What made it readable / pleasant.** Its community explicitly values the fact that English-speaking brains are expert at skimming English, and that "code is read a lot more than it's written" ([Inform forum](https://intfiction.org/t/the-first-thing-you-need-to-understand-about-inform-is/59698)). For descriptive world-building — defining objects, properties, relations — the prose form is genuinely delightful. It is arguably the most successful *literary* programming language.

**What failed / was awkward.** The same forum thread admits the tension: "exquisitely natural forms of expression (syntactic sugar) can hide in plain view the code structures being used. This can be a little frustrating when you're trying to understand not *what* something does, but *how* it does it." Other reported problems:
- Users "were never sure if something was written right or not because of how free the syntax was... instead of memorizing just the function and argument order, you had to memorize an arbitrary number of prepositions. And you couldn't even tell what a piece of 'code' was doing" ([Hacker News](https://news.ycombinator.com/item?id=50203161)).
- "It's not easy to discover even what the syntax is" ([Stack Overflow](https://stackoverflow.com/questions/885097/natural-programming-language-what-would-you-like-to-see)).
- A blog post specifically analyzes Inform 7 against the Principle of Least Surprise ([procyonic.org](https://procyonic.org/blog/on-inform-7-natural-language-programming-and-the-principle-of-least-surprise)).

**Transferable lesson.** Two things. First, **syntactic sugar that conceals control flow hurts maintainers and models alike** — keep the execution structure visible. Second, the Inform 7 parser succeeds because it has a *closed* vocabulary of patterns that it teaches you ("you need to learn those patterns"); the moment you invite open-ended English, writers lose the ability to predict validity. Be like Inform 7's pattern catalog, not like English.

---

## 6. Gherkin / Cucumber (Given/When/Then)

**Syntax approach.** A line-oriented DSL with a tiny closed keyword set — `Feature`, `Background`, `Scenario`, `Scenario Outline`, `Examples`, `Given`, `When`, `Then`, `And`, `But`, `*` — followed by arbitrary domain text. Each step is bound at runtime to a "step definition" in a conventional language. Gherkin has been translated into 70+ languages ([Cucumber reference](https://cucumber.io/docs/gherkin/reference), [opensource.com](https://opensource.com/article/23/2/gherkin-language-developers)).

```gherkin
Scenario: Withdraw within balance
  Given my account has a balance of £430
  When I withdraw £20
  Then my account has a balance of £410
```

**What made it readable / pleasant.** A non-programmer can read and write it. The structure carries meaning: `Given` = precondition, `When` = interaction, `Then` = observable outcome at a system boundary ([Autemos](https://www.autemos.com/en/blogs/gherkin-syntax), [PICKLES paper](https://arxiv.org/html/2604.26572v1)). The discipline it imposes is productive: "avoid talking about user interaction in `Given`s," and "`Then` checks observable outcomes." Cucumber deliberately rejects duplicate step text across keywords, which "forces you to come up with a less ambiguous, more clear domain language" ([Cucumber docs](https://cucumber.io/docs/gherkin/reference)).

**What failed / was awkward.**
- **Keywords are ignored when matching step definitions.** `Given there is money in my account` and `Then there is money in my account` are duplicates. The keyword is reader-facing semantics only, not part of the binding key — a genuine design wart ([Cucumber docs](https://cucumber.io/docs/gherkin/reference), [Autemos](https://www.autemos.com/en/blogs/gherkin-syntax)).
- Ambiguous step definitions are a common runtime error: `{int}` and `{long}` both match `3`, so the run fails ([Medium example](https://medium.com/@kaustubh.saha/bdd-is-not-only-natural-language-programming-with-gherkin-9f3b3d1f081b)).
- Natural-language ambiguity remains: "its lack of logical accuracy increases the likelihood of mistakes as written language is translated into logically exact (and unforgiving) code" ([TestQuality](https://testquality.com/bdd-is-not-only-gherkin-or-cucumber)).
- Teams often skip writing good scenarios, so the claimed collaboration benefit evaporates.

**Transferable lesson.** This is the single best template for our language: **a closed, verbose, fixed vocabulary of structural markers; free-form natural language only in well-defined slots; every statement explicitly bound to deterministic behavior; duplicate/ambiguous bindings rejected at compile time.** Also note the defect to *avoid*: if a keyword changes the reader's understanding, it must participate in resolution — do not throw it away at match time.

---

## 7. Natural-language programming research (1960s–present)

**Syntax approach.** A long lineage: SHRDLU in a restricted "blocks world" with a small vocabulary; Woods' augmented transition networks; Schank's conceptual dependency theory and 1970s conceptual ontologies; 2000s systems translating restricted English to Python via Combinatory Categorial Grammar; NaLIR, an interactive NL-to-relational-database interface; and the SNAPL 2017 line that treats natural language *associated with* a program as extractable formal specification ([NLP history](https://en.wikipedia.org/wiki/History_of_natural_language_processing), [Stanford CS224N history](https://web.stanford.edu/class/cs224n/slides_w26/cs224n-2026-lecture01-history.pdf), [CoRE related-work survey](https://arxiv.org/html/2405.06907v1), [NaLIR](https://sigmodrecord.org/publications/sigmodRecord/1603/pdfs/04_Understand_RH_Li.pdf), [SNAPL 2017](https://drops.dagstuhl.de/storage/00lipics/lipics-vol071-snapl2017/LIPIcs.SNAPL.2017.4/LIPIcs.SNAPL.2017.4.pdf)).

**What made it readable / pleasant.** The successful systems all **restricted the world**. SHRDLU worked because a blocks world has a handful of objects, properties, and actions. NaLIR's key design choice was to *explain* how a query would be processed and, when ambiguous, generate multiple interpretations for the user to choose from rather than guessing.

**What failed / was awkward.** Overpromising and ambiguity. The 1966 ALPAC report found a decade of machine-translation research had failed to meet expectations and funding collapsed. The CoRE survey notes natural language's "inherent vagueness, ambiguity, and verbosity" as the central obstacle to an interpreter. Automatic extraction from Javadoc achieved 88% precision but only 59% recall in Toradocu — revealing that NL-derived specs are partial at best ([SNAPL paper](https://drops.dagstuhl.de/storage/00lipics/lipics-vol071-snapl2017/LIPIcs.SNAPL.2017.4/LIPIcs.SNAPL.2017.4.pdf)).

**Transferable lesson.** Two: **constrain the ontology**, and **ask for disambiguation instead of silently choosing an interpretation**. For an LLM-authored language, the second is cheap — the model can be asked to restate the ambiguous phrase explicitly — and the first is a design decision about how large your standard library is.

---

## 8. LLM-oriented and "pseudocode as code" efforts

### 8.1 SudoLang / PseudoLang (2023–)

A prompt idiom combining natural language with simple coding conventions — commands as phrases with parentheses, template strings, pipe operators. Its own selling point: "the goal... is to provide an easily understandable and interpretable structure to communicate with the GPT-4 AI model... If you understand natural language, you can infer almost all of the meaning" ([Medium / JavaScript Scene](https://medium.com/javascript-scene/sudolang-a-powerful-pseudocode-programming-language-for-llms-d64d42aa719b)). There is no canonical parser, no validator, and no stable specification; it is a family of prompt patterns that evolved through conversation. **Lesson:** pseudocode-as-prompt is great for intent capture and terrible as a durable artifact. Convert it to something checkable.

### 8.2 CoRE / AIOS Compiler (2024)

A research system that uses an LLM *as the interpreter*, unifying natural-language programming, pseudocode programming, and flow programming under one representation. It defines "programming syntax that structures natural language instructions logically," adds external memory to reduce redundancy, and lets the model invoke tools ([arXiv 2405.06907](https://arxiv.org/abs/2405.06907)). This is the most direct precedent for "LLM as the primary consumer." **Lesson:** you can move ambiguity from compile time into runtime reasoning, but you pay for it in nondeterminism, cost, latency, and un-reproducible execution. If you take this route, pin the model/version, record traces, and keep a deterministic IR for anything that must be replayed.

### 8.3 Nanolang and the "we need specifications, not languages" argument

A tiny language designed explicitly to be *targeted* by coding LLMs. The accompanying Hacker News discussion contains the sharpest framing: "we don't need new languages, but new ways to create specifications... an LLM can act as a pseudocode to code translator, where the pseudocode can tolerate a mixture of code-like and natural language specification... it allows tolerance to syntax mistakes or in the worst case, natural language if needed. In other words, I think LLMs don't need new languages" ([HN thread](https://news.ycombinator.com/item?id=46684958)). **Lesson:** treat the human's natural language and the model's pseudocode as *specification*, and make the formal language a low-friction compilation target. Deliberately allow a forgiving front-end mode.

### 8.4 DSLs as an LLM harness (2024–2026)

This is the most directly applicable contemporary body of work.

- Martin Fowler / Unmesh Joshi argue that a DSL with a small surface leaves "very little room to hallucinate," that the generated DSL becomes the artifact humans maintain, and that "even if the LLM hallucinates, the internal DSL will fail to compile allowing LLM to correct the errors made" ([martinfowler.com](https://martinfowler.com/articles/llm-and-dsls.html)). They describe two phases: an LLM *helps build* the DSL, then becomes a natural-language interface *to* it.
- Microsoft's DSL-Copilot pattern: LLM generates DSL code → the DSL parser/compiler validates → errors are fed back for correction until valid. Exposing the schema/grammar to the model helps, "though they format responses in correct structure, validation remains essential." Their bridge advice: start in pseudocode or a familiar language, then translate with explicit syntax guidance ([Azure devblog](https://devblogs.microsoft.com/all-things-azure/ai-coding-agents-domain-specific-languages)).
- Constrained decoding: compile a JSON Schema/grammar into a state machine and mask invalid next tokens. This makes structural failures "architecturally impossible" rather than merely unlikely; one team reported reducing post-processing errors from 32% to 0.4%, and OpenAI reported 100% schema-following on a complex benchmark versus under 40% with prompt-only instructions ([GMI Cloud](https://www.gmicloud.ai/en/blog/structured-output-for-llm-inference-json-schema-enforcement-constrained-decoding-and-parse-failure-rates), [tianpan.co](https://tianpan.co/blog/2026/04/16/grammar-constrained-generation-output-reliability), [zeroentropy.dev](https://zeroentropy.dev/concepts/constrained-decoding)).
- But: **"valid is not correct."** Constrained decoding eliminates structural errors only; it cannot fix a model that misunderstands the task. Prefer flat schemas over deep nesting; prefer required fields with explicit `null` over optional fields; avoid unnecessary decision points ([GMI Cloud](https://www.gmicloud.ai/en/blog/structured-output-for-llm-inference-json-schema-enforcement-constrained-decoding-and-parse-failure-rates), [arXiv 2609.23742](https://arxiv.org/html/2609.23742v1)).
- Real-world DSLs can be brutal even for frontier models: scientific simulation DSLs like LAMMPS fail on small deviations in command order or structure ([arXiv 2603.20630](https://arxiv.org/html/2603.20630v1)).

**Transferable lesson.** Design the language so that it is (a) small enough to put its entire grammar in the prompt, (b) mechanical enough to compile to a grammar for constrained decoding, (c) validated on every edit with localized errors, and (d) simple enough that a wrong program is usually an *obvious* wrong program.

### 8.5 "Natural Language Programming" as theory (2026)

A November 2026 paper coins NLPg and frames prompts as "dynamic cognitive artefacts" externalizing goals, constraints, assumptions, validation criteria, and intermediate reasoning, with prompts acting as "dialogic working memory" ([arXiv 2611.23106](https://arxiv.org/abs/2611.23106)). It is conceptual rather than a language design, but it reinforces a practical point: **prompts already are a de facto programming language** — one with no grammar, no error messages, and no version control. Our language should be what that de facto language becomes when you give it structure.

---

## 9. Designing for an LLM as the primary reader/writer

This is the part that matters for us. My position, stated bluntly: **almost every human-friendly optimization in language design is either neutral or actively harmful for an LLM, and most LLM-friendly optimizations are also good for humans once you get used to them.** Below are concrete, opinionated properties.

### 9.1 Optimize for next-token predictability, not glanceability

Humans scan; models predict. A model writes token by token, so what matters is how strongly the already-written prefix constrains the next token. Choose constructs where, after seeing `define function `, the model knows a name comes next; after `with parameters `, it knows a typed list comes next; after `end function`, it knows the construct is closed. Every point where several equally plausible continuations exist is a coin flip, and a long chain of coin flips is a corrupted program.

**Implication:** prefer a *left-to-right deterministic* grammar. Avoid constructs where you must look ahead to the end of a statement to know how to parse its beginning.

### 9.2 Terse human-optimized syntax is pure downside

This is worth being blunt about. For a model:

- **Token cost is nearly free.** A 30% longer program costs a fraction of a cent and a few hundred milliseconds. A 5% higher error rate costs a debugging cycle, a retry, or a silent wrong answer.
- **Brevity destroys redundancy.** `a+=1` packs four decisions into four characters; `set the counter to the counter plus one` gives the model four chances to notice it's about to do the wrong thing. Redundancy is error-correcting code.
- **Symbols are training-data-dilute.** Every language uses `=`, `()`, `{}`, `;`, `->` differently. A model must infer which dialect it's in from context. English keywords in a fixed vocabulary are less overloaded across the corpus.
- **Terse syntax has high branching factor.** `x = y[z]` has a dozen plausible continuations. `set x to entry z of y` has maybe two.
- **There is no human to impress.** No one is reading this at 3am trying to save keystrokes. The only "ergonomics" that matter are correctness and editability.

So: **verbose, descriptive, fixed keywords. No abbreviations, no operator soup, no clever punctuation.** If a human complains it's wordy, that is a feature being correctly priced.

### 9.3 Explicit, balanced, unmistakable delimiters

Use explicit open/close pairs with unique tokens: `begin ... end`, `define ... end define`, `if ... then ... otherwise ... end if`. Every construct should be bracketed so a model can check locally that it closed what it opened.

- Never make whitespace significant (no off-side rule; no "indentation determines scope") — indentation gets mangled by prompts, diffs, and copy/paste.
- Never rely on automatic semicolon insertion or line-ending inference.
- One statement per line, terminated by an explicit token. No "comma for a non-indented single command" tricks.
- Delimiters must be *reserved* — a user identifier can never be `end` or `then`.

### 9.4 Regular grammar with few special cases

- Aim for LL(1)/LR(1)-ish: no backtracking, no "parse it one way then reinterpret."
- No operator precedence table. If order matters, write nested constructs explicitly: `set x to (a plus b) times c`, or better, three statements with named intermediates.
- No contextual keywords. A word means the same thing everywhere.
- No overloading, no implicit coercions, no "this syntax means X in a `Given` block and Y in a `Then` block" (the Gherkin wart).
- One canonical way to express each construct. If synonyms exist, the formatter normalizes them to one form — the model should never have to choose between equally valid spellings.
- The entire grammar should fit comfortably in a prompt (a few dozen rules). If it doesn't, you have too many special cases. Publish it as a machine-readable grammar so it can also drive constrained decoding.

### 9.5 Verbose descriptive keywords, fixed argument roles

Keywords should be whole English words that describe their job: `define`, `declare`, `set`, `add`, `remove`, `if`, `otherwise`, `repeat`, `for each`, `while`, `return`, `report`, `expect`. Prepositions are acceptable **only from a fixed closed list** (`of`, `to`, `from`, `in`, `with`) with one meaning each — never "an arbitrary number of prepositions" as in Inform 7.

Use labeled roles rather than bare positional arguments:

```
call send_email with recipient = user.email, subject = "Welcome", body = greeting
```

not `send_email(user.email, "Welcome", greeting)`. Labeled roles let a model recover from a mistake and let the validator give a precise error.

### 9.6 Unambiguous parse — no natural-language freedom in executable text

Natural language ambiguity is not a theoretical worry; it is the primary historical failure mode of every language in this survey. Concretely ban:

- **Anaphora and implicit subjects:** no `it`, `they`, `the above`, `that value`. Every reference names a variable.
- **Unbound definites:** no `the user` unless exactly one `user` has been declared in the current scope. `the` should be a compile-time lookup, not a guess.
- **Garden paths and modals:** no `should`, `might`, `try to`, `as needed` in executable statements. A statement either happens or it doesn't.
- **Plural/quantifier ambiguity:** no "some", "a few", "most" in code. Use explicit counts or `for each`.
- **Negation scope:** `not` binds to exactly one immediately following expression, with parentheses required for compounds.
- **Synonym drift:** the model's preferred word for a concept changes across versions and contexts. Fix one word per concept in the language, and reject the rest with a suggestion.

Put the *human's* natural language in a clearly marked, non-executable slot — comments, docstrings, `description:` fields, rationale blocks — where it provides intent and can be read by both model and human but never silently affects control flow. This is the Gherkin split done right.

### 9.7 Immediate error feedback for self-correction

This is the single highest-leverage structural property, because an LLM can iterate. Design the error system as part of the language:

- **Parse on every increment**, even incomplete fragments. Report the *first* error with an exact location and a short list of tokens/constructs that were legal there ("expected `then` or `otherwise` after condition").
- **Validate identifiers immediately**: undefined names, duplicate declarations, type misuse, unreachable code. These are cheap checks and catch most model mistakes.
- **Separate structural, semantic, and policy errors** so feedback is actionable. "Line 12: `end if` has no matching `if`" is fixable; "syntax error" is not.
- **Make the feedback machine-readable** so the harness can loop: generate → parse → feed errors back → regenerate, à la DSL-Copilot.
- **Make invalid syntax impossible where the serving stack allows it** with grammar-constrained decoding. This eliminates structural failures entirely; it does not eliminate wrong intent, so keep the semantic validator.
- Prefer **reject-and-repair** over **guess-and-continue**. A forgiving parser that silently accepts `colour = "red"` as `color` will produce programs that look right and behave differently.

Corollary: **the error vocabulary is part of the language specification.** Write it down, test it, and include common error examples in the model's context.

### 9.8 Expose the grammar and examples in context

Give the model: (1) the complete compact grammar, (2) a canonical "hello world" plus one example of every construct, (3) the standard library signatures, (4) the anti-patterns and banned phrasings. A language small enough for this to fit in one prompt is a language an LLM can use reliably. If your spec needs a retrieval system, the model will half-remember it and improvise.

### 9.9 Deterministic, testable semantics; the LLM is not the runtime

Prefer a real compiler/interpreter with reproducible behavior. If an LLM must act as interpreter (CoRE-style):

- pin the model and version, set temperature to zero, log the full trace;
- keep a deterministic IR that can be replayed without the model;
- treat model-interpreted steps as untrusted and assert on their outputs;
- never use model interpretation for security-, money-, or safety-critical decisions.

### 9.10 Make the artifact diffable and locally editable

Models edit by rewriting spans. Support that:

- one construct per line; no multi-statement lines;
- canonical formatting enforced by a formatter (so diffs don't contain whitespace noise);
- stable, explicit ordering — no hash-order or environment-dependent output;
- explicit imports/dependencies; no ambient global state;
- names declared before use; no forward references requiring inference.

### 9.11 Keep the surface area small on purpose

Every construct is a place to fail. A language with 20 constructs and a 300-function standard library will see most errors in the library, not the syntax. Expose domain concepts through a *small* set of composable primitives plus typed schemas, rather than hundreds of special-purpose verbs. This is the COBOL lesson inverted: resist the 300 reserved words.

### 9.12 The risks of "natural language" specifically — and how to contain them

| Risk | Historical example | Containment |
|---|---|---|
| Multiple valid phrasings → writer can't predict validity | AppleScript, Inform 7 | One canonical spelling; formatter normalizes |
| Reserved-word collisions with user names | AppleScript `yes` | Reserved namespace/sigil; reject collisions at declaration |
| Ambiguous reference resolution | HyperTalk `me`/`target`, Gherkin duplicate steps | Explicit names; keywords participate in binding; reject ambiguous matches |
| Syntactic sugar hides control flow | Inform 7 | Keep structure visible; no hidden rewrite rules |
| Per-library vocabulary drift | AppleScript app dictionaries | Closed core vocabulary; libraries extend *types*, not syntax |
| "Valid but wrong" from unconstrained generation | All LLM DSL work | Semantic validation, tests, constrained decoding, adversarial examples |
| Overpromising what the language understands | ALPAC 1966, NL-to-SQL | Document the closed world explicitly; fail loudly outside it |

---

## 10. A concrete sketch of the style I would adopt

Illustrative only — not a proposal to adopt verbatim. Notice: explicit delimiters, labeled roles, closed keywords, one statement per line, no precedence, natural language parked in `description`, and a validator-friendly shape.

```
define workflow "checkout"
  description: "Charge the customer and send a receipt."   # non-executable intent

  declare order        as Order
  declare customer     as Customer
  declare total        as Money

  set total to call calculate_total with order = order
  if total is greater than customer.credit_limit then
    report "credit limit exceeded" with code = "E42"
    return failure
  end if

  repeat for each item in order.items do
    call reserve_inventory with item = item, quantity = item.quantity
  end repeat

  call charge with customer = customer, amount = total, currency = "GBP"
  call send_receipt with customer = customer, order = order, total = total

  expect charge.status is "approved"
  expect receipt.sent_at is not empty
end workflow
```

Every line is independently parseable; every construct is closed; every name is declared; every call is labeled; the "expect" lines are executable assertions at an observable boundary (the Gherkin lesson); and the human-readable intent lives in a slot the compiler ignores.

---

## 11. Design checklist

- [ ] One canonical spelling per construct; no synonyms or optional prepositions.
- [ ] Explicit balanced delimiters; whitespace insignificant; one statement per line.
- [ ] Keywords are reserved and visually distinct; user names cannot collide.
- [ ] No implicit context, no dynamic scope, no contextual name resolution.
- [ ] No operator precedence; nested explicit expressions instead.
- [ ] No anaphora, unbound `the`, modals, or quantifiers in executable text.
- [ ] Natural language allowed only in marked, non-executable slots.
- [ ] Entire grammar publishable in a prompt and as a machine-readable grammar.
- [ ] Parser emits precise, localized errors with expected-token lists on every increment.
- [ ] Validate ambiguous/duplicate bindings at compile time (the Gherkin bug, fixed).
- [ ] Generate/parse/fix loop supported; optionally grammar-constrained decoding.
- [ ] Small, closed core vocabulary; libraries extend types and values, never syntax.
- [ ] Deterministic semantics and replayable IR; LLM never the interpreter of record.
- [ ] Stable canonical formatting for diff-based editing.

---

## Sources

Primary / authoritative:
- [Wikipedia: COBOL](https://en.wikipedia.org/wiki/COBOL); [IBM: What is COBOL?](https://www.ibm.com/think/topics/cobol)
- [Wikipedia: SQL](https://en.wikipedia.org/wiki/SQL); [IBM: What is SQL?](https://www.ibm.com/think/topics/structured-query-language); [dbt Labs: A brief history of SQL](https://www.getdbt.com/blog/a-brief-history-of-sql)
- [HyperTalk formal syntax appendix (PDF)](http://www.memoryhole.net/~kyle/newwebsite/Curriculum_Vitae_files/hypertalk.pdf); [HyperTalk 2.2: The Book](http://www.jaedworks.com/hypercard/HT2-2TB); [Tricks of the HyperTalk Masters](http://www.jaedworks.com/hypercard/HT-Masters/scripting.html)
- [Cook et al., "AppleScript: A Language for the Rest of Us?" (PDF)](https://www.cs.utexas.edu/~wcook/Drafts/2006/ashopl.pdf); [AppleScript Language Guide](https://developer.apple.com/library/archive/documentation/AppleScript/Conceptual/AppleScriptLangGuide/introduction/ASLR_intro.html)
- [Inform 7 official site](https://ganelson.github.io/inform-website); [Learn Inform 7 in Y Minutes](https://learnxinyminutes.com/inform7)
- [Cucumber Gherkin reference](https://cucumber.io/docs/gherkin/reference)
- [CoRE / AIOS Compiler, arXiv:2405.06907](https://arxiv.org/abs/2405.06907)
- [SNAPL 2017: Natural Language is a Programming Language](https://drops.dagstuhl.de/storage/00lipics/lipics-vol071-snapl2017/LIPIcs.SNAPL.2017.4/LIPIcs.SNAPL.2017.4.pdf); [NaLIR / SIGMOD Record](https://sigmodrecord.org/publications/sigmodRecord/1603/pdfs/04_Understand_RH_Li.pdf); [VLDB NL2SQL survey](https://www.vldb.org/pvldb/vol13/p1737-kim.pdf)
- [Martin Fowler: DSLs Enable Reliable Use of LLMs](https://martinfowler.com/articles/llm-and-dsls.html); [Azure: AI Coding Agents and DSLs](https://devblogs.microsoft.com/all-things-azure/ai-coding-agents-domain-specific-languages); [arXiv:2611.23106](https://arxiv.org/abs/2611.23106)

Community / anecdotal (lower confidence, useful as symptom reports):
- [Hacker News: "The foolishness of natural language programming (1978)"](https://news.ycombinator.com/item?id=50203161); [Hacker News: Nanolang](https://news.ycombinator.com/item?id=46684958)
- [RedSweater: Apple's Script](https://redsweater.com/blog/502/apples-script); [Andy Kong: Learning AppleScript](https://andykong.org/blog/applescripts1); [Automators Talk](https://talk.automators.fm/t/is-it-worth-it-to-learn-applescript-at-this-point-and-time/6834)
- [Inform forum: "The first thing you need to understand about Inform"](https://intfiction.org/t/the-first-thing-you-need-to-understand-about-inform-is/59698); [procyonic.org: Inform 7 and POLS](https://procyonic.org/blog/on-inform-7-natural-language-programming-and-the-principle-of-least-surprise)
- [SudoLang](https://medium.com/javascript-scene/sudolang-a-powerful-pseudocode-programming-language-for-llms-d64d42aa719b)
- [GMI Cloud: constrained decoding](https://www.gmicloud.ai/en/blog/structured-output-for-llm-inference-json-schema-enforcement-constrained-decoding-and-parse-failure-rates); [tianpan.co: grammar-constrained generation](https://tianpan.co/blog/2026/04/16/grammar-constrained-generation-output-reliability); [zeroentropy.dev: constrained decoding](https://zeroentropy.dev/concepts/constrained-decoding)
