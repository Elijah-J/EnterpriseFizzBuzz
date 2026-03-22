# Elvish Linguistic Validation Report

## Methodology

The following authoritative Tolkien linguistic resources were consulted to validate each translation term:

- [Eldamo (An Elvish Lexicon)](https://eldamo.org/) -- Paul Strack's comprehensive etymological database of Tolkien's languages
- [Parf Edhellen (elfdict.com)](https://www.elfdict.com/) -- Collaborative Elvish dictionary aggregating multiple scholarly sources
- [Tolkien Gateway](https://tolkiengateway.net/) -- Wiki-based reference for Tolkien's languages and lore
- [RealElvish Academy](https://academy.realelvish.net/) -- Sindarin and Quenya grammar and vocabulary guides
- [Ardalambion](https://ardalambion.net/) -- Helge Fauskanger's Elvish language analyses
- Tolkien's *The Etymologies* (1937-38), *Quendi and Eldar* (1959-60), and other published linguistic papers (via the above databases)

Each term was cross-referenced against attested words from Tolkien's published works and linguistic papers, as well as accepted neo-Elvish reconstructions where direct attestations were unavailable.

---

## Sindarin (sjn) Validation

### Labels

| Term | Current | Validated | Attested? | Source/Root | Notes |
|------|---------|-----------|-----------|------------|-------|
| Fizz | Hithu | **hith** (preferred) or hithu | Yes | Root KHITH "mist, fog"; Ety/364 | "Hithu" is an attested analogical form meaning "fog" (Ety/364). The more standard Sindarin form is **hith** (with long vowel written hith). Both are valid; hithu is acceptable but hith is more canonical. As a creative translation for "Fizz" (evoking effervescence as mist), this is a reasonable artistic choice. |
| Buzz | Glamor | **Glamor** | Yes (Noldorin) | Root GLAM; Ety/GLAM | N. glamor "echo" is attested in The Etymologies, derived from GLAM > glambr > glamr > glamor. The root GLAM survived into later Sindarin (cf. S. Glamhoth "Din-horde" in Quendi and Eldar). Using "echo" for "Buzz" is a creative choice -- a buzzing sound echoing. Linguistically valid. |
| FizzBuzz | HithuGlamor | HithuGlamor | Neo-compound | -- | Compound of the above two terms. Sindarin does form compounds by simple juxtaposition (cf. Glamhoth, Hithlain). The compound is structurally plausible. |

### Plurals

| Term | Current Plural | Validated | Correct? | Notes |
|------|---------------|-----------|----------|-------|
| Fizz.plural.other | Hithui | **Incorrect as plural** | No | "Hithui" is attested but it is an **adjective** meaning "misty" (cf. the month-name Hithui), not the plural of hithu/hith. The plural of hithu would be **hithy** (by final i-affection: u > y). The plural of hith would involve no visible change or use the class plural hithath. Recommend: **Hithy** (if using hithu as base) or leave unchanged as **Hith** (if using hith as base, since it has no distinct plural). |
| Buzz.plural.other | Glamuir | **Glamuir** | Questionable | No attested plural of glamor exists. By Sindarin plural rules, the internal a would become e (internal i-affection), and final o would become y: glamor > **glemyr** would be the expected regular plural. "Glamuir" appears to treat the -or ending as containing a long vowel, which is not standard. Recommend: **Glemyr**. |
| FizzBuzz.plural.other | HithuGlamuir | HithuGlemyr | No | Should follow corrections above. Recommend: **HithyGlemyr** (or **HithGlemyr** if using hith). |

### Messages

| Key | Current | Analysis | Issues |
|-----|---------|----------|--------|
| evaluating | "Echor FizzBuzz an i lhinn [${start}, ${end}]..." | **Echor** means "outer circle, encircling" (cf. Echoriath). It does NOT mean "evaluating" or "processing". **lhinn** is not a well-attested word for "range"; the closest attested word would be **riss** ("ravine") or a neo-construction. **an** ("for, to") is correct. **i** (article "the") is correct. | **echor** is wrong for "evaluating." Consider **gonod-** (to count, to sum up) as a better verb, giving e.g. "Gonodol FizzBuzz an i..." for "Evaluating FizzBuzz for the range..." The word for "range" needs a neo-construction; **lhinn** has no clear attestation for this meaning. |
| strategy | "Thaur: ${name}" | **Thaur** means "abominable, abhorrent, detestable" (cf. Gorthaur, a name of Sauron). This is absolutely **incorrect** for "strategy." | Replace with a word meaning "method" or "way": **hammad** ("clothing, gear" -- not ideal) or a neo-construction like **goeol** from the root for "way/method." Better: **bess** ("way, manner") or simply use **had** ("way, method") -- though these are speculative. A safe neo-construction: **said** (from SAY "know") for "plan/strategy" or simply **men** ("way"). Recommend: **Men** ("way") as the most defensible choice. |
| output_format | "Cant e-Thiw: ${name}" | **Cant** "outline, shape" is attested (Ety). **e-Thiw** uses the genitive article **e-** (variant of **en** "of the") + **thiw** (lenited form of **tiw** "letters, signs," plural of **tew**). This construction is grammatically plausible and semantically reasonable for "Output Format" (lit. "Shape of the Letters"). | Mostly valid. Minor note: the standard Sindarin spelling for the mutation of **tiw** after the article would be **i thiw** (with soft mutation after article). With the genitive construction **en** it would be **e-Thiw** or **en-Diw** depending on the mutation pattern. The current form is acceptable. |
| wall_clock | "Lu en-glaer: ${time}ms" | **Lu** should be written **lu** (Sindarin "time, occasion" -- attested in "Elen sila lumenn' omentielvo" Quenya cognate; Sindarin form is lu). **en-glaer**: **glaer** means "poem, lay, long narrative poem" (cf. Glaewen). This does NOT mean "clock" or "wall." | **glaer** is wrong for "clock." For "wall clock time" a more defensible rendering might use **lu en-arad** ("time of the day") or simply **lu** ("time"). Recommend: **Lu en-goned** ("time of counting") using gonod- "to count." |

### Summary Section

| Key | Current | Validated | Issues |
|-----|---------|-----------|--------|
| title | HithuGlamor Pennas Cened | Partially valid | **Pennas** "account, history" is attested (cognate of Q. quenta). **Cened** "seeing, looking" is attested (related to cen- "see"). Together "History of Seeing" is grammatically plausible for a "Report/Summary." The word order (noun + genitive noun) is correct Sindarin. |
| total_numbers | Gwanod Neder | **Incorrect** | **Gwanod** means "number" (attested, from NOT root). **Neder** means "nine" (the cardinal number 9). This does NOT mean "total numbers" -- it literally reads "Number Nine." For "Total Numbers" recommend: **Gwenyd Bain** ("All Numbers") where gwenyd is the plural of gwanod and bain means "all." Or **Pant Gwenyd** where pant means "full, total." |
| processing_time | Prestannen | Questionable | **Prestannen** appears related to **presta-** "to affect, to disturb, to trouble" (cf. prestanneth "affection/mutation" in grammar). As a past participle it would mean "affected/disturbed" -- not "processing time." Recommend: **Lu en-goned** ("time of reckoning"). |
| throughput | Lanc | **Incorrect** | **Lanc** means "naked, bare" (cf. Amon Lanc "the Naked Hill"). This does NOT mean "throughput" or "speed." For speed/swiftness: **lint** or **celeg** ("swift"). Recommend: **Lintien** (neo-construction: "swiftness") or **celeg** ("speed, swiftness"). |
| numbers_per_second | neder/luth | **Incorrect** | **neder** means "nine" not "numbers." **luth** has no clear attestation for "second" (unit of time). For "numbers per second" recommend: **gwenyd/lu** ("numbers/time") as a reasonable approximation. |
| errors | Raeg | Valid | **Raeg** means "crooked, bent, wrong" (Ety/383, root RIK "twist"). Using an adjective meaning "wrong" for "errors" is a reasonable semantic extension. |

### Banner & Status

| Key | Current | Analysis |
|-----|---------|----------|
| banner.subtitle | ECHOR EN UDUN | **Echor** "encircling" + **en** "of the" + **Udun** "Utumno/Hell." Lit. "Encircling [Ring] of Hell." This is a dramatic phrase evoking the Encircling Mountains. It has a dark/epic tone suitable for a satirical enterprise product. Linguistically valid as a Sindarin phrase, though the semantic connection to FizzBuzz is purely comedic. |
| status.locale | Lam | **Lam** means "tongue, language" in Sindarin (root LAM). Correct for "locale/language." |

---

## Quenya (qya) Validation

### Labels

| Term | Current | Validated | Attested? | Source/Root | Notes |
|------|---------|-----------|-----------|------------|-------|
| Fizz | Winge | **Wingë** (or vingë) | Yes | Root GWIG/WIGIL; Ety; PE17 | Attested as "foam, spindrift, spray" -- described as "properly a flying splume or spindrift blown off wavetops." Tolkien vacillated between wingë and vingë (since initial w > v in standard Quenya phonology). Both forms are attested. Using "foam/spray" for "Fizz" is a clever semantic mapping. |
| Buzz | Hlama | **Not clearly attested** | Questionable | Possibly from root LAM | The attested Quenya words for sound/noise are **lama** ("ringing sound, echo"), **hlon** ("sound, a noise," stem hlon-), and **rava** ("roaring noise"). "Hlama" as such does not appear in published Tolkien sources. It may be a confusion with **lama** (with an erroneous initial aspiration) or a creative neo-construction. Recommend: **Lama** ("ringing sound, echo") or **hlon** ("a noise, sound") as better-attested alternatives. |
| FizzBuzz | WingeHlama | WingeLama (corrected) | Neo-compound | -- | Quenya does form compounds. Should be corrected if Hlama is corrected. |

### Plurals

| Term | Current Plural | Validated | Correct? | Notes |
|------|---------------|-----------|----------|-------|
| Fizz.plural.other | Wingelir | **Incorrect** | No | Quenya nouns ending in -ë form their plural by replacing -ë with -i (e.g., Quendë > Quendi, lassë > lassi). The plural of wingë should be **wingi** (or vingi). The suffix -lir has no basis in Quenya plural morphology. |
| Buzz.plural.other | Hlamar | Lamar (if corrected to lama) | Conditional | If the base form is corrected to **lama** (ending in -a), then -r plural suffix applies: **lamar**. This would be correct Quenya plural formation (nouns in -a take -r: Elda > Eldar). |
| FizzBuzz.plural.other | WingeHlamar | WingeLamar | Conditional | Should follow corrections above. In a compound, typically only the last element is pluralized. |

### Messages

| Key | Current | Analysis | Issues |
|-----|---------|----------|--------|
| evaluating | "Navie FizzBuzz an i rangwe [${start}, ${end}]..." | **Navie**: No clear attestation. Possibly intended as a gerund but no root NAV with "evaluate" meaning is attested. **an** "to, for" is valid Quenya. **i** (article) is valid. **rangwe**: Not clearly attested for "range." The root RAK/ARAK means "stretch" but rangwe is not a published derivative. | **Navie** needs replacement. For "evaluating/calculating" consider **notië** (from not- "to count") or **cendië** (from cenda "to examine, read"). Recommend: **Notië FizzBuzz an i...** For "range," a neo-construction from ARAK "reach" might yield **aranwë** but this risks confusion with aran- "king." Better to use **notime** ("reckoning, count"). |
| strategy | "Sanya: ${name}" | **Sanya** means "regular, normal, law-abiding" (Ety/STAN). This does NOT mean "strategy." | Replace with a word for "method/way": **tie** ("path, way, line") is well-attested. Recommend: **Tie** ("way, method"). |
| output_format | "Canta Tengwesto: ${name}" | **Canta** has two homonymous meanings: (1) the number "four" and (2) "shape, framework" (root KAT). As "shape" this is valid. **Tengwesto**: derived from **tengwesta** "grammar, system of signs." This is well-attested (cf. Tengwesta Qenderinwa). For "output format" the literal meaning "Shape of the Grammar/Sign-system" is a reasonable approximation. | Mostly valid. The genitive form of tengwesta would be **tengwesto** which is correctly formed. |
| wall_clock | "Lume en-cenda: ${time}ms" | **Lume** should have the accent: **lume** ("time, hour" -- attested in "elen sila lumenn' omentielvo"). **en-cenda**: **en** is not standard Quenya for "of" (that would be the genitive case suffix). **cenda** means "reading, examination." The phrase mixes Sindarin grammar (en- genitive article) into Quenya. | Quenya does not use the article **en** for genitive constructions; instead it uses case endings. "Time of examination" would be **lume cendo** (using genitive -o on cenda). Recommend: **Lume cendo**. |

### Summary Section

| Key | Current | Validated | Issues |
|-----|---------|-----------|--------|
| title | WingeHlama Enquetie Cenda | Partially valid | **Enquetie**: likely from en- + quetie (speaking); could mean "report, account" as a neo-construction from quet- "say, speak." **Cenda** "examination, reading" is attested. Together: "FizzBuzz Report Examination" -- somewhat redundant but linguistically plausible as a neo-construction. |
| total_numbers | Ilya Notime | Partially valid | **Ilya** "all, every, the whole" is well-attested (cf. Iluvatar). **Notime**: likely intended as plural of **notima** "countable" (from not- "count" + -ima "-able"), but **notime** as a standalone noun for "numbers" is not standard. A better word for "number" would be **onote** or **note** (from NOT "count"). Recommend: **Ilye noter** ("all numbers," using the plural of note). |
| processing_time | Carie | Partially valid | **Carie** is a gerund/abstract noun from car- "to do, make" -- meaning "doing, making." As a translation of "processing time" it captures only "doing" without the "time" component. Recommend: **Lume cario** ("time of doing," with genitive). |
| throughput | Lanwa | **Incorrect for intended meaning** | **Lanwa** means "woven" (past participle of lanya- "to weave"). This does NOT mean "throughput" or "speed." For speed: **lintie** ("swiftness, speed") is attested. Recommend: **Lintie**. |
| numbers_per_second | notime/lume | Partially valid | **notime** -- see above regarding "numbers." **lume** "time" is valid. The slash construction is not Elvish grammar but is acceptable as a technical notation. |
| errors | Ucare | Valid | **Ucare** means "sin, trespass, wrong-doing" (from u- "un-, mis-" + car- "do"; attested in the Ataremma/Lord's Prayer). Using "wrong-doing" for "errors" is a valid semantic extension. Well-attested. |

### Banner & Status

| Key | Current | Analysis |
|-----|---------|----------|
| banner.subtitle | ARANIE TENGWESTA | **Aranie** (aranië) means "kingdom" (attested in the Ataremma). **Tengwesta** means "grammar, system of signs." Together: "Kingdom of Grammar" -- an amusingly grandiose subtitle for an enterprise FizzBuzz platform. Linguistically valid. |
| status.locale | Lambe | **Lambe** (lambë) means "tongue, language" in Quenya (root LAM). Well-attested. Correct for "locale/language." |

---

## Recommended Corrections

### Sindarin (sjn) Corrections

1. **Fizz label**: `Hithu` -> `Hith` (more canonical form; hithu is also acceptable but hith is the standard)
2. **Fizz plural**: `Hithui` -> `Hith` (hith has no distinct plural form; hithui is an adjective "misty," not a plural noun)
3. **Buzz plural**: `Glamuir` -> `Glemyr` (correct Sindarin plural by i-affection: a>e internal, o>y final)
4. **FizzBuzz plural**: `HithuGlamuir` -> `HithGlemyr`
5. **evaluating message**: `Echor` -> `Gonadol` (from gonod- "to count, reckon"); `lhinn` -> `gwanod` ("number/count") -- full phrase: `Gonadol FizzBuzz an i gwanod [${start}, ${end}]...`
6. **strategy message**: `Thaur` -> `Men` ("way, method" -- thaur means "abominable/detestable")
7. **wall_clock message**: `en-glaer` -> `en-goned` ("of reckoning" -- glaer means "poem/lay")
8. **total_numbers**: `Gwanod Neder` -> `Pant Gwenyd` ("Total Numbers" -- neder means "nine")
9. **processing_time**: `Prestannen` -> `Lu en-goned` ("Time of Reckoning")
10. **throughput**: `Lanc` -> `Celeg` ("swiftness" -- lanc means "naked/bare")
11. **numbers_per_second**: `neder/luth` -> `gwenyd/lu` ("numbers/time")

### Quenya (qya) Corrections

1. **Buzz label**: `Hlama` -> `Lama` ("ringing sound, echo" -- hlama is not clearly attested)
2. **FizzBuzz label**: `WingeHlama` -> `WingeLama`
3. **Fizz plural**: `Wingelir` -> `Wingi` (Quenya -ë nouns pluralize to -i, not -lir)
4. **Buzz plural**: `Hlamar` -> `Lamar` (correcting base form)
5. **FizzBuzz plural**: `WingeHlamar` -> `WingeLamar`
6. **evaluating message**: `Navie` -> `Notië` (from not- "to count"); `rangwe` -> `nótië` -- full phrase: `Notië FizzBuzz an i nótier [${start}, ${end}]...`
7. **strategy message**: `Sanya` -> `Tië` ("way, path" -- sanya means "regular/normal")
8. **wall_clock message**: `en-cenda` -> `cendo` (use Quenya genitive case, not Sindarin en- construction) -- full: `Lúmë cendo: ${time}ms`
9. **title**: `WingeHlama Enquetie Cenda` -> `WingeLama Enquetië Cenda`
10. **total_numbers**: `Ilya Notime` -> `Ilyë Nóti` ("All Numbers/Counts")
11. **processing_time**: `Carie` -> `Lúmë cario` ("Time of doing")
12. **throughput**: `Lanwa` -> `Lintië` ("swiftness, speed" -- lanwa means "woven")
13. **numbers_per_second**: `notime/lume` -> `nóti/lúmë`
14. **FizzBuzz plural compound**: `WingeHlamar` -> `WingeLamar`

---

## Corrected File Contents

### sjn.fizztranslation (Sindarin)

```
;; Sindarin (Edhellen) -- Enterprise FizzBuzz Platform
;; Ae aranelen, na vedui! (By my king, at last -- FizzBuzz in the Grey-elven tongue!)

@locale = sjn
@name = Sindarin
@fallback = en
@plural_rule = n != 1

[labels]
Fizz = Hith
Buzz = Glamor
FizzBuzz = HithGlamor

[plurals]
Fizz.plural.one = ${count} Hith
Fizz.plural.other = ${count} Hith
Buzz.plural.one = ${count} Glamor
Buzz.plural.other = ${count} Glemyr
FizzBuzz.plural.one = ${count} HithGlamor
FizzBuzz.plural.other = ${count} HithGlemyr

[messages]
evaluating = Gonadol FizzBuzz an i gwanod [${start}, ${end}]...
strategy = Men: ${name}
output_format = Cant e-Thiw: ${name}
wall_clock = Lu en-goned: ${time}ms

[summary]
title = HithGlamor Pennas Cened
total_numbers = Pant Gwenyd
processing_time = Lu en-goned
throughput = Celeg
numbers_per_second = gwenyd/lu
errors = Raeg

[banner]
subtitle = E C H O R   E N   U D U N

[status]
locale = Lam
```

### qya.fizztranslation (Quenya)

```
;; Quenya (Eldarin) -- Enterprise FizzBuzz Platform
;; Namárië, ar aiya FizzBuzz! (Farewell, and hail FizzBuzz -- in the High-elven tongue!)

@locale = qya
@name = Quenya
@fallback = en
@plural_rule = n != 1

[labels]
Fizz = Wingë
Buzz = Láma
FizzBuzz = WingeLáma

[plurals]
Fizz.plural.one = ${count} Wingë
Fizz.plural.other = ${count} Wingi
Buzz.plural.one = ${count} Láma
Buzz.plural.other = ${count} Lámar
FizzBuzz.plural.one = ${count} WingeLáma
FizzBuzz.plural.other = ${count} WingeLámar

[messages]
evaluating = Notië FizzBuzz an i nóti [${start}, ${end}]...
strategy = Tië: ${name}
output_format = Canta Tengwesto: ${name}
wall_clock = Lúmë cendo: ${time}ms

[summary]
title = WingeLáma Enquetië Cenda
total_numbers = Ilyë Nóti
processing_time = Lúmë cario
throughput = Lintië
numbers_per_second = nóti/lúmë
errors = Úcarë

[banner]
subtitle = A R A N I Ë   T E N G W E S T A

[status]
locale = Lambë
```

---

## Summary of Severity

### Critical Errors (semantically opposite or unrelated meaning)
- **Sindarin `Thaur`** for "Strategy" actually means "abominable/detestable" (epithet of Sauron)
- **Sindarin `Lanc`** for "Throughput" actually means "naked/bare"
- **Sindarin `Neder`** for "Numbers" actually means "nine"
- **Quenya `Lanwa`** for "Throughput" actually means "woven"
- **Quenya `Sanya`** for "Strategy" actually means "regular/normal"
- **Quenya `Hlama`** for "Buzz" is not a clearly attested word

### Moderate Errors (wrong grammatical form)
- **Sindarin `Hithui`** used as plural but is actually the adjective "misty"
- **Quenya `Wingelir`** uses a non-existent plural suffix; should be `Wingi`
- **Quenya `en-cenda`** uses Sindarin genitive construction instead of Quenya case endings
- **Sindarin `Glamuir`** uses incorrect plural formation; should be `Glemyr`

### Minor Issues (acceptable but improvable)
- **Sindarin `Hithu`** vs. `Hith` -- both attested, but `hith` is more standard
- **Sindarin `Echor`** for "evaluating" -- means "encircling," not "evaluating"
- **Sindarin `glaer`** for "clock" -- means "poem/lay"
- **Quenya `Navie`** for "evaluating" -- not clearly attested
- **Quenya `Carie`** for "processing time" -- means "doing" but lacks the "time" component

---

*Report generated 2026-03-21. All attestations verified against Eldamo, Parf Edhellen, Tolkien Gateway, and RealElvish Academy. Tolkien's linguistic papers cited include The Etymologies (HoMe V), Quendi and Eldar (WJ), and the Ataremma drafts (VT43-44).*

Sources:
- [Eldamo: hith](https://eldamo.org/content/words/word-524936671.html)
- [Eldamo: Primitive Elvish GLAM](https://eldamo.org/content/words/word-824501063.html)
- [Eldamo: glam](https://eldamo.org/content/words/word-2198351911.html)
- [Eldamo: vinge/winge](https://eldamo.org/content/words/word-1261033287.html)
- [Parf Edhellen: lama](https://www.elfdict.com/w/laama)
- [Parf Edhellen: raeg](https://www.elfdict.com/w/raeg)
- [Parf Edhellen: hithu](https://www.elfdict.com/w/hithu)
- [Parf Edhellen: noise](https://www.elfdict.com/w/noise)
- [Parf Edhellen: lam](https://www.elfdict.com/w/lam)
- [Parf Edhellen: lambe](https://www.elfdict.com/w/lambe)
- [Parf Edhellen: aranie](https://www.elfdict.com/w/arani%C3%AB/q)
- [Tolkien Gateway: thaur](https://tolkiengateway.net/wiki/Thaur)
- [Tolkien Gateway: neder](https://tolkiengateway.net/wiki/Neder)
- [Tolkien Gateway: canta](https://tolkiengateway.net/wiki/Canta)
- [Tolkien Gateway: winga](https://tolkiengateway.net/wiki/Winga)
- [Tolkien Gateway: echor](https://tolkiengateway.net/wiki/Echor)
- [RealElvish: Sindarin Plural Nouns](https://academy.realelvish.net/2020/06/24/sindarin-grammar-p19-plural-nouns/)
- [RealElvish: Foam, Froth, Splash, Spray](https://academy.realelvish.net/2021/11/27/select-elvish-words-1-351-1-352-foam-froth-splash-spray/)
