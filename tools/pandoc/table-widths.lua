-- Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
--
-- This source code is protected under international copyright law.  All rights
-- reserved and protected by the copyright holders.
--
-- This file is confidential and only available to authorized individuals with the
-- permission of the copyright holders.  If you encounter this file and do not have
-- permission, please contact the copyright holders and delete this file.
--
-- Pandoc filter: give width-less tables shared, content-derived column widths.
--
-- The gfm reader records no column widths for pipe tables, whatever --columns is
-- set to. With every width zero, pandoc's LaTeX writer falls back to `l` columns:
--
--     \begin{longtable}[]{@{}lll@{}}
--
-- `l` is a natural-width column, so cells never wrap and each column grows to its
-- widest cell. A Description column of prose then pushes the table far past the
-- text block - our README overflowed by up to 789pt, about 10.9in.
--
-- Two decisions shape the widths this assigns:
--
-- 1. Weighting is the SQUARE ROOT of the widest cell, not the width itself.
--    Sharing out in direct proportion lets one column of prose take nearly
--    everything - a 120-character Description against a 25-character Location
--    claims 73% and leaves the short column wrapping every row onto three lines.
--    Prose reflows happily over several lines; a short label reads badly broken
--    up. The square root keeps the ordering while compressing the ratio.
--
-- 2. Measurements are POOLED across every table sharing a header row, and one
--    width set is applied to all of them. Measured per table, each section's
--    table gets its own proportions and the columns visibly jump from category
--    to category. Pooling makes Command / Location / Description line up down the
--    whole document, which is what makes it read as one table split by heading
--    rather than a dozen unrelated ones.
--
-- Usage:
--   pandoc README.md -f gfm -o README.pdf --pdf-engine=xelatex \
--     --lua-filter=tools/pandoc/table-widths.lua

-- Smallest share any single column may take, before renormalising.
local MIN_SHARE = 0.12

local function has_explicit_widths(tbl)
  -- Respect widths the source actually specified; only fill in the blanks.
  for _, spec in ipairs(tbl.colspecs) do
    if type(spec[2]) == "number" and spec[2] > 0 then
      return true
    end
  end
  return false
end

--- Identify tables that should share one set of widths.
-- Keyed on column count plus header text, so the Command/Location/Description
-- tables pool together while a differently shaped table keeps its own fit.
local function group_key(tbl)
  local parts = {}
  local first = tbl.head.rows[1]
  if first then
    for _, cell in ipairs(first.cells) do
      parts[#parts + 1] = pandoc.utils.stringify(cell.contents)
    end
  end
  return #tbl.colspecs .. ":" .. table.concat(parts, "|")
end

local function scan_rows(rows, ncols, widest)
  for _, row in ipairs(rows) do
    local col = 1
    for _, cell in ipairs(row.cells) do
      if col <= ncols then
        -- stringify gives the rendered text, so link syntax and emphasis
        -- markers do not inflate the measurement.
        local len = #pandoc.utils.stringify(cell.contents)
        if len > widest[col] then
          widest[col] = len
        end
      end
      col = col + (cell.col_span or 1)
    end
  end
end

local function measure(tbl, ncols, widest)
  scan_rows(tbl.head.rows, ncols, widest)
  for _, body in ipairs(tbl.bodies) do
    scan_rows(body.body, ncols, widest)
  end
end

local function shares_from(widest, ncols)
  local weights = {}
  local total = 0
  for i = 1, ncols do
    weights[i] = math.sqrt(widest[i])
    total = total + weights[i]
  end

  -- Apply the floor first, then renormalise, so the shares still sum to 1.
  local shares = {}
  local sum = 0
  for i = 1, ncols do
    local share = weights[i] / total
    if share < MIN_SHARE then
      share = MIN_SHARE
    end
    shares[i] = share
    sum = sum + share
  end
  for i = 1, ncols do
    shares[i] = shares[i] / sum
  end
  return shares
end

local function eligible(tbl)
  return #tbl.colspecs > 0 and not has_explicit_widths(tbl)
end

function Pandoc(doc)
  local widest_by_group = {}

  -- Pass 1: pool the widest cell per column across each group of like tables.
  doc:walk({
    Table = function(tbl)
      if not eligible(tbl) then
        return nil
      end
      local ncols = #tbl.colspecs
      local key = group_key(tbl)
      local widest = widest_by_group[key]
      if not widest then
        widest = {}
        for i = 1, ncols do
          widest[i] = 1
        end
        widest_by_group[key] = widest
      end
      measure(tbl, ncols, widest)
      return nil
    end,
  })

  -- Pass 2: derive each group's widths once, then stamp them on every member.
  local shares_by_group = {}
  return doc:walk({
    Table = function(tbl)
      if not eligible(tbl) then
        return nil
      end
      local ncols = #tbl.colspecs
      local key = group_key(tbl)
      local shares = shares_by_group[key]
      if not shares then
        shares = shares_from(widest_by_group[key], ncols)
        shares_by_group[key] = shares
      end
      local specs = {}
      for i = 1, ncols do
        specs[i] = { tbl.colspecs[i][1], shares[i] }
      end
      tbl.colspecs = specs
      return tbl
    end,
  })
end
