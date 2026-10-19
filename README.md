# pgfornament – Drawing of Vectorian ornaments with PGF/TikZ

Release 1.4 2026/10/17

## Description

This package allows the drawing of Vectorian ornaments (196) with pgf/tikz.
Version 1.4 adds a family of 16 Celtic knots (`object=celtic`, public domain, from publicdomainvectors.org) and a script `tools/svg2pgf.py` to convert svg, eps or pdf drawings into new ornaments.
The documentation presents the syntax and parameters of the macro "pgfornament".
About tikzrput package:
This package contains the rput macro that can be used to place objects. This macro does similar actions of the rput macro from pstricks. Here this macro needs tikz to work.
With this new version comes a new family of ornaments.
Chennan Zhang drew the motifs using a CAD application, re-drew them in TikZ, and granted permission for these to be turned into a library pgfornament-han suitable for use with the pgfornament package by LianTze Lim.
It is now possible to use directly the library for Chinese traditional motifs and patterns.

## About tikzrput package

This package contains the `\rput` macro that can be used to place objects. This
macro does similar actions of the `\rput` macro from pstricks. Here this macro
needs `tikz` to work.

## Licence

The packages may be modified and distributed under the terms and
conditions of the [LaTeX Project Public
License](https://www.latex-project.org/lppl/), version 1.3c or greater.
See the files `LICENSE` and `lppl-1-3c.txt`.

## Installation

The package `pgfornament` and `tikzrput` are present in `TeXLive` and `MiKTeX`, use the
package manager to install.

You can experiment with the `pgfornament` and `tikzrput` packages by placing all of the
distribution files in the directory containing your current tex file.

For manual instalation all files must be moved into the different directories in your
installation `TDS` tree or in your `TEXMFHOME`:

```
  doc/*.*             -> TDS:doc/latex/pgfornament/*.*
  latex/*.*           -> TDS:tex/latex/pgfornament/*.*
  generic/*/*.*       -> TDS:tex/generic/pgfornament/*/*.*
  tools/svg2pgf.py    -> TDS:doc/latex/pgfornament/tools/ (optional)
```

## File names

Since version 1.4 all the runtime files begin with `pgfornament`
(TeX Live rule): `pgfornament.sty`, the libraries
`pgfornament-lib-<family>.code.tex` and the ornaments
`pgfornament-<family><n>.pgf`. The package `tikzrput.sty` is a separate
package of the bundle. The documentation is `pgfornament-doc.pdf`.

## How to use it

To use the package `pgfornament`, place the following lines in the preamble of
your LaTeX document.

```
\usepackage{pgfornament}
```

## Documentation

Documentations for `pgfornament` and `tikzrput`  are available on CTAN and in your TeX distribution.


