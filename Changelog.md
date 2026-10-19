# Changelog — pgfornament

All notable changes to this package are documented here.
`tikzrput` has its own version (1.1).

---
## [1.4] — 2026/10/17
### Added
- New family `celtic`: 16 Celtic knots (`object=celtic`, public domain, from publicdomainvectors.org).
- Script `tools/svg2pgf.py` to convert svg, eps or pdf drawings into new ornaments.

### Changed
- All runtime files now begin with `pgfornament` (TeX Live rule): libraries `pgfornament-lib-<family>.code.tex` (instead of `pgflibrary<family>.code.tex`) and ornaments `pgfornament-<family><n>.pgf` (instead of `<family><n>.pgf`). The old names are still accepted for families created by users; `\callornament{vectorian1.pgf}` still works.
- The documentation is now `pgfornament-doc.tex` / `pgfornament-doc.pdf` (instead of `ornaments`).

### Fixed
- Spurious spaces in `\newpgfornamentfamily`, the environment `newfamily`, `\pgfornamenthline` and `\pgfornamentvline`.
- The libraries no longer change the catcode of `@` with `\makeatletter`/`\makeatother` (the previous catcode is restored).
- `\pgf@@ornament` and `\callornament` share the same definitions (`\pgfornament@shortcuts`); `\k` and `\ubb` are now available for all families; the library of the family `am` no longer redefines `\pgf@@ornament`.
- `\pgfornamentline`: the number of ornaments is an integer, the color is reset at each call, no more global macro `\nbo`.
- `calc` library loaded (needed by `\pgfornamenthline` and `\pgfornamentvline`).
- Family `am`: wrong dimensions of the ornaments 1 and 2 (option `width`/`height`), duplicate entry removed.
- Wrong bounding box of `vectorian170`, `pgfhan64` and `pgfhan76`.

## [1.3] — 2024/08/14
### Fixed
- Spurious space (reported by Tibor Tómács); corrections of the documentation.

## [1.2]
### Fixed
- Spurious space (reported by LianTze Lim).

## [1.00]
### Added
- Han ornaments (`pgfhan`) and some new macros; new examples in the documentation.
- Thanks to Pablo González L. for his help with Git.

## [0.21]
### Fixed
- `pgfornament.sty`: `ornament/at` replaces the key `at` (conflict with `at` from pgf) — thanks to Christian Feuersänger.
- Documentation: bugs in the examples (reported by Peter Zimmermann); new section “Problem” describing some difficulties.
