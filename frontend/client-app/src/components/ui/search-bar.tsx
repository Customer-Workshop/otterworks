import { useState, useCallback, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Search, X } from "lucide-react";
import { searchApi } from "@/lib/api";
import { cn } from "@/lib/utils";

const MIN_SUGGEST_CHARS = 2;
const SUGGEST_DEBOUNCE_MS = 200;

export function SearchBar() {
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const containerRef = useRef<HTMLFormElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const handle = setTimeout(() => setDebouncedQuery(query.trim()), SUGGEST_DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [query]);

  const { data: suggestions = [] } = useQuery({
    queryKey: ["search", "suggest", debouncedQuery],
    queryFn: () => searchApi.suggest(debouncedQuery),
    enabled: debouncedQuery.length >= MIN_SUGGEST_CHARS,
    staleTime: 30000,
  });

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const goToSearch = useCallback(
    (term: string) => {
      const trimmed = term.trim();
      if (!trimmed) return;
      setQuery(trimmed);
      setOpen(false);
      navigate(`/search?q=${encodeURIComponent(trimmed)}`);
    },
    [navigate]
  );

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      goToSearch(activeIndex >= 0 ? suggestions[activeIndex] : query);
    },
    [activeIndex, suggestions, query, goToSearch]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || suggestions.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => (i + 1) % suggestions.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => (i <= 0 ? suggestions.length - 1 : i - 1));
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const showDropdown = open && debouncedQuery.length >= MIN_SUGGEST_CHARS && suggestions.length > 0;

  return (
    <form ref={containerRef} onSubmit={handleSubmit} className="relative w-full" role="search">
      <Search
        size={18}
        className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
      />
      <input
        type="text"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setActiveIndex(-1);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKeyDown}
        placeholder="Search files, documents..."
        role="combobox"
        aria-expanded={showDropdown}
        aria-controls="search-suggestions"
        aria-autocomplete="list"
        aria-activedescendant={activeIndex >= 0 ? `search-suggestion-${activeIndex}` : undefined}
        className="w-full pl-10 pr-10 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-otter-500 focus:border-transparent transition"
      />
      {query && (
        <button
          type="button"
          onClick={() => {
            setQuery("");
            setOpen(false);
          }}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
          aria-label="Clear search"
        >
          <X size={16} />
        </button>
      )}
      {showDropdown && (
        <ul
          id="search-suggestions"
          role="listbox"
          className="absolute left-0 right-0 top-full mt-1 z-40 bg-white border border-gray-200 rounded-lg shadow-lg overflow-hidden"
        >
          {suggestions.map((suggestion, index) => (
            <li
              key={suggestion}
              id={`search-suggestion-${index}`}
              role="option"
              aria-selected={index === activeIndex}
              onMouseDown={(e) => e.preventDefault()}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => goToSearch(suggestion)}
              className={cn(
                "flex items-center gap-2 px-3 py-2 text-sm text-gray-800 cursor-pointer",
                index === activeIndex ? "bg-otter-50" : "hover:bg-gray-50"
              )}
            >
              <Search size={14} className="text-gray-400 shrink-0" />
              <span className="truncate">{suggestion}</span>
            </li>
          ))}
        </ul>
      )}
    </form>
  );
}
