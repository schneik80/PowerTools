-- Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
--
-- This source code is protected under international copyright law.  All rights
-- reserved and protected by the copyright holders.
--
-- This file is confidential and only available to authorized individuals with the
-- permission of the copyright holders.  If you encounter this file and do not have
-- permission, please contact the copyright holders and delete this file.
--
-- Pandoc filter: render a Markdown thematic break as a page break.
--
-- The horizontal rules in our Markdown mark section boundaries that are meant to
-- start a new page in print, not to draw a line. Pandoc's default is a literal
-- rule, which in a PDF reads as a stray line mid-page, so replace each one with
-- \newpage.
--
-- Usage:
--   pandoc README.md -f gfm -o README.pdf --pdf-engine=xelatex \
--     --lua-filter=tools/pandoc/hr-to-pagebreak.lua

function HorizontalRule()
  -- RawBlock rather than a string: the LaTeX writer must emit \newpage as a
  -- command, not as escaped literal text.
  return pandoc.RawBlock("latex", "\\newpage")
end
