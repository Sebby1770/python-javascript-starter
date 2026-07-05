const TICK_SOUND_KEY = "taskpulse-pomodoro-tick";
const activeTimers = new Map();

function formatCountdown(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function playTick() {
  if (localStorage.getItem(TICK_SOUND_KEY) !== "true") {
    return;
  }
  try {
    const context = new AudioContext();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.type = "sine";
    oscillator.frequency.value = 880;
    gain.gain.value = 0.04;
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.05);
    oscillator.onended = () => context.close();
  } catch {
    // Audio not available.
  }
}

function notifyComplete(taskTitle) {
  if (!("Notification" in window)) {
    return;
  }
  if (Notification.permission === "granted") {
    new Notification("Pomodoro complete", {
      body: `Time's up for "${taskTitle}"`,
    });
  }
}

export function isTickSoundEnabled() {
  return localStorage.getItem(TICK_SOUND_KEY) === "true";
}

export function setTickSoundEnabled(enabled) {
  localStorage.setItem(TICK_SOUND_KEY, enabled ? "true" : "false");
}

export function requestNotificationPermission() {
  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission();
  }
}

export function getActivePomodoro(taskId) {
  return activeTimers.get(taskId) || null;
}

export function stopPomodoro(taskId) {
  const timer = activeTimers.get(taskId);
  if (!timer) {
    return;
  }
  clearInterval(timer.intervalId);
  activeTimers.delete(taskId);
  if (timer.overlay) {
    timer.overlay.remove();
  }
}

export function startPomodoro({
  task,
  card,
  onComplete,
  onTick,
  onStart,
}) {
  stopPomodoro(task.id);

  const totalSeconds = Math.max(60, task.minutes * 60);
  let remaining = totalSeconds;

  const overlay = document.createElement("div");
  overlay.className = "pomodoro-overlay";
  overlay.innerHTML = `
    <span class="pomodoro-time">${formatCountdown(remaining)}</span>
    <button type="button" class="pomodoro-stop" aria-label="Stop timer">Stop</button>
  `;
  card.append(overlay);

  const timeNode = overlay.querySelector(".pomodoro-time");
  overlay.querySelector(".pomodoro-stop").addEventListener("click", () => {
    stopPomodoro(task.id);
  });

  if (onStart) {
    onStart(task);
  }

  const intervalId = setInterval(() => {
    remaining -= 1;
    timeNode.textContent = formatCountdown(remaining);
    playTick();
    if (onTick) {
      onTick(remaining);
    }

    if (remaining <= 0) {
      stopPomodoro(task.id);
      notifyComplete(task.title);
      if (onComplete) {
        onComplete(task);
      }
    }
  }, 1000);

  activeTimers.set(task.id, { intervalId, overlay, remaining });
  return { stop: () => stopPomodoro(task.id) };
}