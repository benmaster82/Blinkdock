(() => {
  "use strict";

  const states = {
    listening: {
      image: "images/widget-listening.png",
      alt: "Blinkdock listening, with one tracked session and no edited files",
      description: "Ready when you are. One session, quietly listening.",
      terminal: "Ready for your next prompt.",
      files: ["No files touched yet", "Waiting for a new task"],
    },
    working: {
      image: "images/widget-working.png",
      alt: "Blinkdock working, with two tracked sessions and three edited files",
      description:
        "Claude is working. Two sessions tracked, three files touched.",
      terminal: "Running tests for the editor...",
      files: ["E  island.py", "E  file_panel.py", "W  README.md"],
    },
    waiting: {
      image: "images/widget-waiting.png",
      alt: "Expanded Blinkdock widget waiting for user permission",
      description:
        "A session needs your input. Time to return to its terminal.",
      terminal: "Permission needed to continue.",
      files: ["E  island.py", "E  file_panel.py", "W  README.md"],
    },
    done: {
      image: "images/widget-done.png",
      alt: "Expanded Blinkdock widget showing a completed turn",
      description:
        "The turn is complete. The real widget returns to Listening shortly.",
      terminal: "Turn complete. Ready for review.",
      files: ["E  island.py", "E  file_panel.py", "W  README.md"],
    },
  };

  const demo = document.querySelector(".demo");
  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
  const image = document.getElementById("hero-widget");
  const panel = document.getElementById("state-panel");
  const play = document.getElementById("play-demo");
  const description = document.getElementById("state-description");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let timer = null;
  document.querySelector(".demo-controls").hidden = false;

  Object.values(states).forEach((state) => {
    const preload = new Image();
    preload.src = state.image;
  });

  function setState(name) {
    const state = states[name];
    demo.dataset.state = name;
    image.src = state.image;
    image.alt = state.alt;
    image.width = name === "waiting" || name === "done" ? 756 : 440;
    image.height = name === "waiting" || name === "done" ? 120 : 104;
    panel.setAttribute("aria-labelledby", `state-${name}`);
    description.textContent = state.description;
    document.getElementById("terminal-status").textContent = state.terminal;
    const activity = document.getElementById("activity-preview");
    activity.replaceChildren();
    state.files.forEach((file, index) => {
      if (index) activity.append(document.createElement("br"));
      activity.append(document.createTextNode(file));
    });
    tabs.forEach((tab) => {
      const active = tab.dataset.state === name;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
    });
  }

  function stopDemo() {
    window.clearInterval(timer);
    timer = null;
    play.setAttribute("aria-pressed", "false");
    play.setAttribute("aria-label", "Play state demo");
    play.title = "Play state demo";
    play.firstElementChild.className = "icon i-play";
    description.setAttribute("aria-live", "polite");
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => {
      stopDemo();
      setState(tab.dataset.state);
    });
    tab.addEventListener("keydown", (event) => {
      let next;
      if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft")
        next = (index + tabs.length - 1) % tabs.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = tabs.length - 1;
      if (next === undefined) return;
      event.preventDefault();
      tabs[next].focus();
      tabs[next].click();
    });
  });

  play.addEventListener("click", () => {
    if (timer) {
      stopDemo();
      return;
    }
    play.setAttribute("aria-pressed", "true");
    play.setAttribute("aria-label", "Pause state demo");
    play.title = "Pause state demo";
    play.firstElementChild.className = "icon i-pause";
    description.setAttribute("aria-live", "off");
    const advance = () => {
      const names = Object.keys(states);
      setState(names[(names.indexOf(demo.dataset.state) + 1) % names.length]);
    };
    advance();
    timer = window.setInterval(advance, reducedMotion.matches ? 4500 : 3000);
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopDemo();
  });
  reducedMotion.addEventListener("change", stopDemo);

  const copy = document.getElementById("copy-install");
  const feedback = document.getElementById("copy-feedback");
  let feedbackTimer;
  copy.addEventListener("click", async () => {
    window.clearTimeout(feedbackTimer);
    const code = document.getElementById("install-commands");
    try {
      await navigator.clipboard.writeText(code.textContent.trim());
      feedback.textContent = "Copied to clipboard.";
      copy.firstElementChild.className = "icon i-check";
      copy.setAttribute("aria-label", "Installation commands copied");
    } catch {
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(code);
      selection.removeAllRanges();
      selection.addRange(range);
      feedback.textContent = "Commands selected. Press Ctrl+C to copy.";
    }
    feedbackTimer = window.setTimeout(() => {
      feedback.textContent = "";
      copy.firstElementChild.className = "icon i-copy";
      copy.setAttribute("aria-label", "Copy installation commands");
    }, 5000);
  });
})();
