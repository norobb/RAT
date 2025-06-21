import React, { useState, useRef, useEffect, useMemo } from "react";

const COMMANDS = [
  { name: "help", description: "Zeigt die Hilfe an" },
  { name: "exec", description: "Führe einen Shell-Befehl aus" },
  { name: "screenshot", description: "Screenshot des Bildschirms" },
  { name: "download", description: "Datei herunterladen (Pfad angeben)" },
  { name: "upload", description: "Datei zum Client hochladen" },
  { name: "history", description: "Browserverlauf anzeigen" },
  { name: "keylogger", description: "Keylogger-Log anzeigen" },
  { name: "ls", description: "Verzeichnis auflisten" },
  { name: "systeminfo", description: "Systeminformationen anzeigen" },
  { name: "shutdown", description: "Client herunterfahren" },
  { name: "restart", description: "Client neustarten" },
  { name: "screenstream_start", description: "Live-Screen starten" },
  { name: "screenstream_stop", description: "Live-Screen stoppen" },
];

type CommandInputProps = {
  value?: string;
  onChange?: (val: string) => void;
  onCommandSubmit?: (val: string) => void;
};

export default function CommandInput({
  value,
  onChange,
  onCommandSubmit,
}: CommandInputProps) {
  const [input, setInput] = useState(value ?? "");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const suggestionRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    if (typeof value === "string" && value !== input) setInput(value);
  }, [value]);

  const filteredCommands = useMemo(() => {
    if (!input.startsWith("/")) return [];
    const query = input.slice(1).toLowerCase();
    return COMMANDS.filter(cmd => cmd.name.startsWith(query));
  }, [input]);

  useEffect(() => {
    setShowSuggestions(input.startsWith("/") && filteredCommands.length > 0);
    setSelectedIndex(0);
  }, [input, filteredCommands.length]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        inputRef.current &&
        !inputRef.current.contains(event.target as Node) &&
        suggestionRef.current &&
        !suggestionRef.current.contains(event.target as Node)
      ) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (showSuggestions) {
      if (e.key === "ArrowDown") {
        setSelectedIndex(i => Math.min(i + 1, filteredCommands.length - 1));
        e.preventDefault();
      } else if (e.key === "ArrowUp") {
        setSelectedIndex(i => Math.max(i - 1, 0));
        e.preventDefault();
      } else if (e.key === "Tab" || e.key === "Enter") {
        if (filteredCommands[selectedIndex]) {
          const cmd = "/" + filteredCommands[selectedIndex].name + " ";
          setInput(cmd);
          onChange?.(cmd);
          setShowSuggestions(false);
          if (e.key === "Enter" && onCommandSubmit) {
            onCommandSubmit(cmd);
          }
          e.preventDefault();
        }
      } else if (e.key === "Escape") {
        setShowSuggestions(false);
      }
    } else if (e.key === "Enter" && onCommandSubmit) {
      onCommandSubmit(input);
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setInput(e.target.value);
    onChange?.(e.target.value);
  };

  return (
    <div style={{ position: "relative" }}>
      <input
        ref={inputRef}
        value={input}
        onChange={handleInputChange}
        onKeyDown={handleKeyDown}
        onBlur={() => setTimeout(() => setShowSuggestions(false), 120)}
        placeholder="Nachricht senden oder / für Befehle"
        style={{ width: "100%" }}
        aria-autocomplete="list"
        aria-controls="command-suggestion-list"
        aria-activedescendant={
          showSuggestions && filteredCommands[selectedIndex]
            ? `command-suggestion-${filteredCommands[selectedIndex].name}`
            : undefined
        }
        autoComplete="off"
      />
      {showSuggestions && (
        <ul
          ref={suggestionRef}
          id="command-suggestion-list"
          role="listbox"
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            background: "#23272a",
            color: "#fff",
            borderRadius: 6,
            margin: 0,
            padding: "4px 0",
            listStyle: "none",
            width: "100%",
            boxShadow: "0 4px 16px #000a",
            zIndex: 1000,
            fontSize: "1em",
          }}
        >
          {filteredCommands.map((cmd, idx) => (
            <li
              id={`command-suggestion-${cmd.name}`}
              key={cmd.name}
              role="option"
              aria-selected={idx === selectedIndex}
              style={{
                padding: "8px 16px",
                background: idx === selectedIndex ? "#5865f2" : "transparent",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
              }}
              onMouseDown={e => {
                e.preventDefault();
                const cmdStr = "/" + cmd.name + " ";
                setInput(cmdStr);
                onChange?.(cmdStr);
                setShowSuggestions(false);
                inputRef.current?.focus();
              }}
              onMouseEnter={() => setSelectedIndex(idx)}
            >
              <span style={{ fontWeight: 600, minWidth: 110 }}>{"/" + cmd.name}</span>
              <span style={{ color: "#b9bbbe", marginLeft: 10, fontSize: "0.97em" }}>{cmd.description}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
