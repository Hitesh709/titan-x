"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Search, X } from "lucide-react"
import api from "@/lib/api"
import type { CompanySearchResult } from "@/types"

interface SymbolAutocompleteProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
  disabled?: boolean
}

export function SymbolAutocomplete({
  value,
  onChange,
  placeholder = "RELIANCE",
  className = "",
  disabled = false,
}: SymbolAutocompleteProps) {
  const [suggestions, setSuggestions] = useState<CompanySearchResult[]>([])
  const [isOpen, setIsOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const debounceRef = useRef<NodeJS.Timeout>()
  const selectedRef = useRef(false)

  const fetchSuggestions = useCallback(async (query: string) => {
    if (!query || query.length < 1) {
      setSuggestions([])
      return
    }
    try {
      setLoading(true)
      const res = await api.get<{ items: CompanySearchResult[]; total: number }>(
        `/companies?search=${encodeURIComponent(query)}&exchange=NSE&limit=10&order_by=symbol`,
      )
      setSuggestions(res.items ?? [])
    } catch {
      setSuggestions([])
    } finally {
      setLoading(false)
    }
  }, [])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const next = e.target.value.toUpperCase()
    if (selectedRef.current) {
      // Value came from a suggestion click — don't reopen the dropdown.
      selectedRef.current = false
      onChange(next)
      return
    }
    onChange(next)
    if (next.length > 0) setIsOpen(true)
  }

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      fetchSuggestions(value)
    }, 150)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [value, fetchSuggestions])

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (inputRef.current && !inputRef.current.contains(e.target as Node) &&
          listRef.current && !listRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen || suggestions.length === 0) {
      if (e.key === "ArrowDown" && suggestions.length > 0) {
        e.preventDefault()
        setIsOpen(true)
        setHighlightedIndex(0)
      }
      return
    }
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault()
        setHighlightedIndex(i => Math.min(i + 1, suggestions.length - 1))
        break
      case "ArrowUp":
        e.preventDefault()
        setHighlightedIndex(i => Math.max(i - 1, 0))
        break
      case "Enter":
        e.preventDefault()
        if (highlightedIndex >= 0) {
          onChange(suggestions[highlightedIndex].symbol)
          setIsOpen(false)
          setHighlightedIndex(-1)
        }
        break
      case "Escape":
        setIsOpen(false)
        setHighlightedIndex(-1)
        break
      case "Tab":
        setIsOpen(false)
        setHighlightedIndex(-1)
        break
    }
  }

  const handleBlur = () => {
    setTimeout(() => {
      setIsOpen(false)
      setHighlightedIndex(-1)
    }, 150)
  }

  const handleFocus = () => {
    if (value.length > 0) setIsOpen(true)
  }

  return (
    <div className={`relative ${className}`} ref={inputRef}>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 size-4" />
        <input
          type="text"
          value={value}
          onChange={handleChange}
          onFocus={handleFocus}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={placeholder}
          className="input-field pl-9 pr-9 text-sm w-full"
          autoComplete="off"
          aria-autocomplete="list"
          aria-controls="symbol-suggestions"
          aria-expanded={isOpen && suggestions.length > 0}
        />
        {value && (
          <button
            type="button"
            onClick={() => onChange("")}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white"
            aria-label="Clear"
          >
            <X size={14} />
          </button>
        )}
      </div>

      {isOpen && suggestions.length > 0 && (
        <ul
          ref={listRef}
          id="symbol-suggestions"
          role="listbox"
          className="absolute z-50 mt-1 w-full glass-card rounded-lg border border-white/10 overflow-hidden max-h-60 overflow-y-auto"
        >
          {suggestions.map((s, i) => (
            <li
              key={s.symbol}
              role="option"
              aria-selected={i === highlightedIndex}
              onMouseEnter={() => setHighlightedIndex(i)}
              onClick={() => {
                selectedRef.current = true
                onChange(s.symbol)
                setIsOpen(false)
                setHighlightedIndex(-1)
                inputRef.current?.focus()
              }}
              className={`px-3 py-2 text-sm cursor-pointer ${
                i === highlightedIndex ? "bg-white/10" : ""
              } hover:bg-white/5`}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-white">{s.symbol}</span>
                {s.company_name && (
                  <span className="text-gray-500 text-xs truncate max-w-[60%] text-right ml-2">{s.company_name}</span>
                )}
              </div>
              {s.sector && <div className="text-[10px] text-gray-500 mt-0.5">{s.sector}</div>}
            </li>
          ))}
        </ul>
      )}

      {isOpen && !loading && value.length >= 1 && suggestions.length === 0 && (
        <div className="absolute z-50 mt-1 w-full glass-card rounded-lg border border-white/10 px-3 py-2 text-sm text-gray-500">
          No symbols found
        </div>
      )}
    </div>
  )
}