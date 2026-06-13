# Build the paper and produce an arXiv-ready submission tarball.
#
#   make            -> agentmem-bench.pdf  (pdflatex + bibtex + pdflatex x2)
#   make arxiv      -> agentmem-bench-arxiv.tar.gz  (self-contained, incl. .bbl)
#   make figures    -> regenerate figures from committed runs (needs matplotlib)
#   make clean      -> remove LaTeX aux files
#   make veryclean  -> also remove the PDF + tarball
#
# Requires a TeX distribution (TeX Live / MacTeX) with pdflatex + bibtex. All
# packages used (natbib, graphicx, booktabs, pifont, microtype, lmodern,
# hyperref) ship with a standard TeX Live and with arXiv's AutoTeX.

PAPER   := agentmem-bench
LATEX   := pdflatex -interaction=nonstopmode -halt-on-error
BIBTEX  := bibtex
FIGS    := figures/capability_heatmap.pdf figures/latency.pdf

.PHONY: all pdf arxiv figures clean veryclean

all: pdf

pdf: $(PAPER).pdf

$(PAPER).pdf: $(PAPER).tex refs.bib $(FIGS)
	$(LATEX) $(PAPER)
	$(BIBTEX) $(PAPER)
	$(LATEX) $(PAPER)
	$(LATEX) $(PAPER)
	@echo "✔ built $(PAPER).pdf"

# Self-contained arXiv upload. We ship the generated .bbl (so arXiv need not run
# BibTeX) plus the .tex and figure PDFs. arXiv compiles with pdflatex by default.
arxiv: pdf
	@test -s $(PAPER).bbl || { echo "ERROR: $(PAPER).bbl is empty/missing; run 'make pdf' first"; exit 1; }
	rm -rf arxiv-build $(PAPER)-arxiv.tar.gz
	mkdir -p arxiv-build/figures
	cp $(PAPER).tex $(PAPER).bbl arxiv-build/
	cp $(FIGS) arxiv-build/figures/
	cd arxiv-build && tar czf ../$(PAPER)-arxiv.tar.gz .
	@echo "✔ wrote $(PAPER)-arxiv.tar.gz  — upload this single file to arXiv"
	@echo "  contents:" && tar tzf $(PAPER)-arxiv.tar.gz | sed 's/^/    /'

figures:
	MPLBACKEND=Agg python3 make_figures.py

clean:
	rm -f $(PAPER).aux $(PAPER).log $(PAPER).out $(PAPER).bbl $(PAPER).blg \
	      $(PAPER).toc $(PAPER).fls $(PAPER).fdb_latexmk
	rm -rf arxiv-build

veryclean: clean
	rm -f $(PAPER).pdf $(PAPER)-arxiv.tar.gz
