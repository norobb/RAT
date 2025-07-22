import React, { useState, useRef, useEffect, useMemo } from "react";

const COMMANDS = [
	{ name: "help", description: "Show available commands", category: "general" },
	{ name: "exec", description: "Execute shell command", category: "system" },
	{ name: "screenshot", description: "Take screenshot", category: "media" },
	{ name: "download", description: "Download file (specify path)", category: "files" },
	{ name: "upload", description: "Upload file to client", category: "files" },
	{ name: "history", description: "Show browser history", category: "info" },
	{ name: "keylogger", description: "Show keylogger data", category: "surveillance" },
	{ name: "ls", description: "List directory contents", category: "files" },
	{ name: "cd", description: "Change directory", category: "files" },
	{ name: "encrypt", description: "Encrypt files/directory", category: "security" },
	{ name: "decrypt", description: "Decrypt files/directory", category: "security" },
	{ name: "systeminfo", description: "Show system information", category: "info" },
	{ name: "process_list", description: "List running processes", category: "system" },
	{ name: "kill_process", description: "Kill process by PID", category: "system" },
	{ name: "network_info", description: "Show network information", category: "network" },
	{ name: "network_scan", description: "Scan network for hosts", category: "network" },
	{ name: "shutdown", description: "Shutdown client", category: "power" },
	{ name: "restart", description: "Restart client", category: "power" },
	{ name: "screenstream_start", description: "Start live screen stream", category: "media" },
	{ name: "screenstream_stop", description: "Stop live screen stream", category: "media" },
	{ name: "scan_cameras", description: "Scan for network cameras", category: "network" },
	{ name: "webcam_start", description: "Start webcam stream", category: "media" },
	{ name: "webcam_stop", description: "Stop webcam stream", category: "media" },
];

type CommandInputProps = {
	value?: string;
	onChange?: (val: string) => void;
	onCommandSubmit?: (val: string) => void;
	placeholder?: string;
	disabled?: boolean;
	className?: string;
};

export default function CommandInput({
	value,
	onChange,
	onCommandSubmit,
	placeholder = "Send message or type / for commands",
	disabled = false,
	className = "",
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
		return COMMANDS.filter((cmd) => 
			cmd.name.toLowerCase().includes(query) || 
			cmd.description.toLowerCase().includes(query) ||
			cmd.category.toLowerCase().includes(query)
		).sort((a, b) => {
			// Prioritize exact matches
			const aExact = a.name.toLowerCase().startsWith(query);
			const bExact = b.name.toLowerCase().startsWith(query);
			if (aExact && !bExact) return -1;
			if (!aExact && bExact) return 1;
			return a.name.localeCompare(b.name);
		});
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
				setSelectedIndex((i) => Math.min(i + 1, filteredCommands.length - 1));
				e.preventDefault();
			} else if (e.key === "ArrowUp") {
				setSelectedIndex((i) => Math.max(i - 1, 0));
				e.preventDefault();
			} else if (e.key === "Tab") {
				if (filteredCommands.length > 0 && filteredCommands[selectedIndex]) {
					const cmd = "/" + filteredCommands[selectedIndex].name + " ";
					setInput(cmd);
					onChange?.(cmd);
					setShowSuggestions(false);
					e.preventDefault();
				}
			} else if (e.key === "Enter") {
				const cmd = input;
				onCommandSubmit?.(cmd);
				e.preventDefault();
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

	const getCategoryColor = (category: string) => {
		const colors: Record<string, string> = {
			general: "#6b7280",
			system: "#ef4444", 
			media: "#8b5cf6",
			files: "#10b981",
			info: "#3b82f6",
			surveillance: "#f59e0b",
			security: "#f97316",
			network: "#06b6d4",
			power: "#dc2626"
		};
		return colors[category] || "#6b7280";
	};

	return (
		<div style={{ position: "relative" }}>
			<input
				ref={inputRef}
				value={input}
				onChange={handleInputChange}
				onKeyDown={handleKeyDown}
				placeholder={placeholder}
				disabled={disabled}
				className={className}
				style={{
					width: "100%",
					outline: showSuggestions ? "2px solid #5865f2" : "none",
				}}
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
					{filteredCommands.length === 0 && (
						<li style={{ padding: "8px 16px", color: "#b9bbbe" }}>
							No commands found
						</li>
					)}
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
							onMouseDown={(e) => {
								e.preventDefault();
								const cmdStr = "/" + cmd.name + " ";
								setInput(cmdStr);
								onChange?.(cmdStr);
								setShowSuggestions(false);
								setSelectedIndex(0);
								inputRef.current?.focus();
							}}
							onMouseEnter={() => setSelectedIndex(idx)}
						>
							<div style={{ display: "flex", alignItems: "center", flex: 1 }}>
								<span 
									style={{ 
										backgroundColor: getCategoryColor(cmd.category),
										color: "white",
										fontSize: "0.7em",
										padding: "2px 6px",
										borderRadius: "3px",
										marginRight: "8px",
										textTransform: "uppercase",
										fontWeight: "bold"
									}}
								>
									{cmd.category}
								</span>
								<span style={{ fontWeight: 600, minWidth: 110 }}>{"/" + cmd.name}</span>
								<span
									style={{ color: "#b9bbbe", marginLeft: 10, fontSize: "0.97em" }}
								>
									{cmd.description}
								</span>
							</div>
						</li>
					))}
				</ul>
			)}
		</div>
	);
}