const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

let appState;
let currentSession = null;
let busy = false;
let toastTimer;
let timerInterval = null;
let timerRemaining = 0;
let timerDeadline = 0;
let timerPaused = false;
let timerMode = "standard";

async function api(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && url !== "/api/me") showAuth("login");
    throw new Error(data.error || `Error ${response.status}`);
  }
  return data;
}

function showToast(message, isError = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("show");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toast.classList.remove("show"), 3600);
}

function openView(name) {
  $$(".view").forEach((view) => view.classList.toggle("active", view.id === `view-${name}`));
  $$(".tab").forEach((tab) => {
    const active = tab.dataset.view === name;
    tab.classList.toggle("active", active);
    if (active) tab.setAttribute("aria-current", "page");
    else tab.removeAttribute("aria-current");
  });
  if (name === "profile") fillProfile();
  document.querySelector(`#view-${name} h2`)?.focus();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function showAuth(mode = "login") {
  appState = null;
  currentSession = null;
  $("#app-shell").hidden = true;
  $("#auth-screen").hidden = false;
  $("#privacy-note").hidden = true;
  $("#logout-button").hidden = true;
  setAuthMode(mode);
}

function setAuthMode(mode) {
  const registering = mode === "register";
  $("#login-form").hidden = registering;
  $("#register-form").hidden = !registering;
  $$(".auth-mode").forEach((button) => {
    const active = button.dataset.authMode === mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  $("#login-message").textContent = "";
  $("#register-message").textContent = "";
}

async function showApp() {
  $("#auth-screen").hidden = true;
  $("#app-shell").hidden = false;
  $("#privacy-note").hidden = false;
  $("#logout-button").hidden = false;
  await loadState();
  openView("panel");
  $("#panel-title").focus();
}

function fillProfile() {
  if (!appState) return;
  $("#candidate-name").value = appState.profile.name || "";
  $("#candidate-level").value = appState.profile.level || "junior";
  $("#target-job").innerHTML = appState.jobOptions.map((job) => `
    <option value="${escapeHTML(job.id)}">${escapeHTML(job.title)} · ${escapeHTML(job.company)}</option>`).join("")
    + '<option value="custom">Otro puesto</option>';
  $("#target-job").value = appState.profile.jobId || "frontend-jr";
  $("#candidate-skills").value = (appState.profile.skills || []).join(", ");
  $("#custom-job-title").value = appState.profile.customJobTitle || "";
  toggleCustomJobField();
  $("#accommodation-options").innerHTML = Object.entries(appState.accommodations).map(([id, label]) => `
    <div class="option">
      <input type="checkbox" id="pref-${id}" name="accommodations" value="${id}"
        ${appState.profile.accommodations.includes(id) ? "checked" : ""}>
      <label for="pref-${id}">${escapeHTML(label)}</label>
    </div>`).join("");
}

function toggleCustomJobField() {
  const isCustom = $("#target-job").value === "custom";
  $("#custom-job-field").hidden = !isCustom;
  $("#custom-job-title").required = isCustom;
}

function escapeHTML(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

function renderJobs(jobs) {
  const featured = jobs.slice(0, 2).map((job) => `
    <article class="job-row">
      <span class="job-icon" aria-hidden="true">${escapeHTML(job.title.slice(0, 1))}</span>
      <div><h4>${escapeHTML(job.title)}</h4><p>${escapeHTML(job.company)} · ${escapeHTML(job.location)}</p></div>
      <span class="match">${job.match}% afin</span>
    </article>`).join("");
  $("#featured-jobs").innerHTML = featured || "<p>Aun no hay vacantes.</p>";

  $("#all-jobs").innerHTML = jobs.map((job) => `
    <article class="card job-card">
      <div class="job-card-top"><span class="icon-tile" aria-hidden="true">${escapeHTML(job.title.slice(0, 1))}</span><span class="match">${job.match}% afin</span></div>
      <h3>${escapeHTML(job.title)}</h3>
      <p class="company-line">${escapeHTML(job.company)} · ${escapeHTML(job.area)}</p>
      <p class="description">${escapeHTML(job.summary)}</p>
      <div class="job-meta"><span>${escapeHTML(job.location)}</span><span>·</span><span>${escapeHTML(job.level)}</span></div>
      <p class="field"><strong>Habilidades:</strong> ${job.skills.map(escapeHTML).join(" · ")}</p>
      <div class="support-wrap" aria-label="Apoyos disponibles">
        ${job.supports.map((support) => `<span class="support-chip">${escapeHTML(appState.accommodations[support] || support)}</span>`).join("")}
      </div>
      <button class="text-button" type="button" data-job-detail="${escapeHTML(job.id)}">Ver por qué coincide <span aria-hidden="true">→</span></button>
      <button class="button button-outline job-practice-button" type="button" data-job-practice="${escapeHTML(job.id)}">Practicar para este puesto</button>
    </article>`).join("");
}

function renderState() {
  const { profile, metrics, jobs } = appState;
  $("#hello-name").textContent = profile.name ? `, ${profile.name}` : "";
  const levelNames = { trainee: "En etapa inicial", junior: "Con algo de experiencia", intermedio: "Experiencia intermedia" };
  $("#profile-level").textContent = `Nivel de experiencia: ${levelNames[profile.level] || "No indicado"}`;
  $("#preference-summary").innerHTML = profile.accommodations.length
    ? profile.accommodations.map((id) => `<li>${escapeHTML(appState.accommodations[id] || id)}</li>`).join("")
    : "<li>Aun no hay preferencias seleccionadas</li>";
  $("#metric-interviews").textContent = metrics.interviews;
  $("#metric-responses").textContent = metrics.responses;
  $("#metric-score").textContent = metrics.responses ? `${metrics.averageScore} / 5` : "—";
  $("#impact-interviews").textContent = metrics.interviews;
  $("#impact-adapted").textContent = metrics.adapted;
  $("#impact-rate").textContent = `${metrics.inclusionRate}%`;
  const selectedJob = profile.jobId === "custom"
    ? profile.customJobTitle
    : (appState.jobOptions.find((job) => job.id === profile.jobId) || {}).title;
  $("#interview-context").textContent = selectedJob ? `Puesto seleccionado: ${selectedJob}` : "Elige un puesto desde tu perfil.";
  updateInterviewAgentCopy(selectedJob);
  renderInterviewHistory(appState.recentInterviews);
  renderJobs(jobs);
  fillProfile();
}

function updateInterviewAgentCopy(selectedJob) {
  if (selectedJob === undefined && appState) {
    selectedJob = appState.profile.jobId === "custom"
      ? appState.profile.customJobTitle
      : (appState.jobOptions.find((job) => job.id === appState.profile.jobId) || {}).title;
  }
  const role = selectedJob || "el puesto que elijas";
  $("#interview-agent-copy").textContent = $("#interview-engine").value === "ollama"
    ? `Ollama genera cinco preguntas y feedback para ${role} en este equipo.`
    : `El asesor por reglas prepara cinco preguntas para ${role} y da sugerencias basadas en habilidades relacionadas.`;
}

function renderInterviewHistory(history) {
  const target = $("#interview-history");
  if (!history.length) {
    target.innerHTML = '<p class="history-empty">Aún no tienes prácticas completadas. Cuando termines una entrevista, aquí verás tu progreso.</p>';
    return;
  }
  target.innerHTML = history.map((item) => {
    const date = item.completedAt ? new Date(item.completedAt).toLocaleDateString("es-MX") : "";
    return `<article class="history-row">
      <div><h4>${escapeHTML(item.jobTitle)}</h4><p>${escapeHTML(date)} · ${item.responses} respuestas evaluadas</p></div>
      <span class="match">${item.average} / 5</span>
    </article>`;
  }).join("");
}

async function loadState() {
  appState = await api("/api/state");
  renderState();
}

function resetInterview() {
  stopTimer();
  currentSession = null;
  $("#interview-intro").hidden = false;
  $("#question-area").hidden = true;
  $("#interview-finished").hidden = true;
  $("#answer-input").value = "";
  $("#answer-feedback").hidden = true;
  $("#timer-status").textContent = "";
}

async function startInterview(jobId = null) {
  const button = $("#start-interview");
  button.disabled = true;
  try {
    timerMode = $("#timer-mode").value;
    const data = await api("/api/interview/start", {
      method: "POST",
      body: JSON.stringify({
        engine: $("#interview-engine").value,
        ...(jobId ? { jobId } : {}),
      }),
    });
    currentSession = data.sessionId;
    $("#interview-intro").hidden = true;
    $("#interview-finished").hidden = true;
    $("#question-area").hidden = false;
    $("#active-job-title").textContent = `${data.agentName} · ${data.jobTitle}`;
    showQuestion(data.question);
  } catch (error) {
    showToast(error.message, true);
  } finally {
    button.disabled = false;
  }
}

function showQuestion(question) {
  stopTimer();
  $("#question-count").textContent = `Pregunta ${question.index + 1} de ${question.total}`;
  const difficultyNames = { easy: "Inicial", intermediate: "Intermedia", advanced: "Avanzada" };
  $("#question-difficulty").textContent = `Dificultad ${difficultyNames[question.difficulty] || "Intermedia"}`;
  $("#progress-bar").setAttribute("aria-valuenow", question.index + 1);
  $("#progress-bar").setAttribute("aria-valuemax", question.total);
  $("#progress-fill").style.width = `${((question.index + 1) / question.total) * 100}%`;
  $("#question-prompt").textContent = question.prompt;
  const isExercise = question.type === "code" || question.type === "exercise";
  $("#technical-task").hidden = !isExercise;
  $("#answer-input").classList.toggle("code-answer", question.type === "code");
  $("#answer-label").textContent = question.type === "code" ? "Tu código y razonamiento" : isExercise ? "Tu propuesta" : "Tu respuesta";
  $("#answer-input").placeholder = question.type === "code"
    ? `Escribe tu solución en ${question.language}, pseudocódigo o una explicación.`
    : isExercise
      ? "Escribe tu respuesta, propuesta o pasos de solución."
      : "Explica tu razonamiento. No hay una respuesta perfecta.";
  $("#task-language").textContent = question.language || "Ejercicio práctico";
  $("#starter-code").textContent = question.starterCode || "";
  $("#timer-panel").hidden = timerMode === "off";
  $("#timer-status").textContent = timerMode === "off"
    ? "Práctica sin cronómetro; continúa a tu ritmo."
    : "";
  const steps = $("#question-steps");
  steps.innerHTML = question.steps.map((step) => `<li>${escapeHTML(step)}</li>`).join("");
  steps.hidden = !question.steps.length;
  $("#answer-input").value = "";
  $("#answer-feedback").hidden = true;
  startTimer(question.timeLimit);
  $("#question-prompt").focus();
}

function formatTime(seconds) {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, "0");
  const remaining = (seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remaining}`;
}

function stopTimer() {
  if (timerInterval !== null) window.clearInterval(timerInterval);
  timerInterval = null;
  timerPaused = false;
}

function renderTimer() {
  $("#timer-display").textContent = formatTime(timerRemaining);
  $("#timer-panel").classList.toggle("timer-warning", timerRemaining <= 30 && timerRemaining > 0);
  if (timerRemaining === 0) {
    stopTimer();
    $("#timer-panel").classList.add("timer-warning");
    $("#timer-toggle").textContent = "Tiempo sugerido terminado";
    $("#timer-toggle").disabled = true;
    $("#timer-status").textContent = "Terminó el tiempo sugerido. Puedes continuar o enviar cuando estés listo/a; no hay penalización.";
  }
}

function startTimer(seconds) {
  stopTimer();
  if (timerMode === "off") return;
  timerRemaining = seconds * (timerMode === "extended" ? 2 : 1);
  timerDeadline = Date.now() + timerRemaining * 1000;
  $("#timer-toggle").textContent = "Pausar cronómetro";
  $("#timer-toggle").disabled = false;
  $("#timer-toggle").setAttribute("aria-pressed", "false");
  renderTimer();
  timerInterval = window.setInterval(() => {
    timerRemaining = Math.max(0, Math.ceil((timerDeadline - Date.now()) / 1000));
    renderTimer();
  }, 250);
}

function toggleTimer() {
  if (timerInterval === null && timerRemaining === 0) return;
  if (timerPaused) {
    timerPaused = false;
    timerDeadline = Date.now() + timerRemaining * 1000;
    $("#timer-toggle").textContent = "Pausar cronómetro";
    $("#timer-toggle").setAttribute("aria-pressed", "false");
    $("#timer-status").textContent = "Cronómetro reanudado.";
    timerInterval = window.setInterval(() => {
      timerRemaining = Math.max(0, Math.ceil((timerDeadline - Date.now()) / 1000));
      renderTimer();
    }, 250);
  } else {
    timerRemaining = Math.max(0, Math.ceil((timerDeadline - Date.now()) / 1000));
    stopTimer();
    timerPaused = true;
    $("#timer-toggle").textContent = "Reanudar cronómetro";
    $("#timer-toggle").setAttribute("aria-pressed", "true");
    $("#timer-status").textContent = "Cronómetro en pausa.";
    renderTimer();
  }
}

async function submitAnswer() {
  if (busy) return;
  const answer = $("#answer-input").value.trim();
  if (answer.length < 4) {
    showToast("Agrega un poco más a tu respuesta antes de continuar.", true);
    $("#answer-input").focus();
    return;
  }
  busy = true;
  const button = $("#submit-answer");
  button.disabled = true;
  button.textContent = "Guardando…";
  try {
    const data = await api("/api/interview/answer", {
      method: "POST",
      body: JSON.stringify({ sessionId: currentSession, answer }),
    });
    stopTimer();
    const feedback = $("#answer-feedback");
    feedback.textContent = `Gracias por compartirlo. ${data.result.feedback}`;
    feedback.hidden = false;
    if (data.finished) {
      $("#question-area").hidden = true;
      $("#interview-finished").hidden = false;
      $("#finish-summary").textContent = `Para ${data.summary.jobTitle}, tu promedio orientativo fue ${data.summary.average} de 5 en ${data.summary.responses} respuestas.`;
      $("#strength-list").innerHTML = data.summary.strengths.length
        ? data.summary.strengths.map((item) => `<span>${escapeHTML(item)}</span>`).join("")
        : "<span>Seguiste la práctica hasta el final</span>";
      await loadState();
      $("#practice-again").focus();
    } else {
      window.setTimeout(() => showQuestion(data.question), 850);
    }
  } catch (error) {
    showToast(error.message, true);
  } finally {
    busy = false;
    button.disabled = false;
    button.innerHTML = 'Enviar respuesta <span aria-hidden="true">→</span>';
  }
}

$("#contrast-toggle").addEventListener("click", (event) => {
  const active = document.body.classList.toggle("high-contrast");
  event.currentTarget.setAttribute("aria-pressed", String(active));
});

$$(".tab").forEach((tab) => tab.addEventListener("click", () => openView(tab.dataset.view)));
$$("[data-open-view]").forEach((button) => button.addEventListener("click", () => openView(button.dataset.openView)));

$$(".auth-mode").forEach((button) => button.addEventListener("click", () => setAuthMode(button.dataset.authMode)));

async function submitAuthForm(event, endpoint, messageSelector) {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = form.querySelector('button[type="submit"]');
  const message = $(messageSelector);
  message.textContent = "";
  submitButton.disabled = true;
  try {
    const body = Object.fromEntries(new FormData(form).entries());
    await api(endpoint, { method: "POST", body: JSON.stringify(body) });
    form.reset();
    await showApp();
  } catch (error) {
    message.textContent = error.message;
    if (endpoint === "/api/login") $("#login-password").focus();
    else $("#register-password").focus();
  } finally {
    submitButton.disabled = false;
  }
}

$("#login-form").addEventListener("submit", (event) => submitAuthForm(event, "/api/login", "#login-message"));
$("#register-form").addEventListener("submit", (event) => submitAuthForm(event, "/api/register", "#register-message"));

$("#logout-button").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    await api("/api/logout", { method: "POST", body: "{}" });
    resetInterview();
    showAuth("login");
    $("#login-email").focus();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    button.disabled = false;
  }
});

$("#profile-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = $("#profile-message");
  message.textContent = "";
  const profile = {
    name: $("#candidate-name").value.trim(),
    level: $("#candidate-level").value,
    jobId: $("#target-job").value,
    customJobTitle: $("#custom-job-title").value.trim(),
    skills: $("#candidate-skills").value.split(",").map((skill) => skill.trim()).filter(Boolean),
    accommodations: $$("input[name=accommodations]:checked").map((input) => input.value),
  };
  try {
    appState.profile = await api("/api/profile", { method: "POST", body: JSON.stringify(profile) });
    await loadState();
    message.textContent = "Preferencias guardadas.";
    showToast("Tus preferencias se guardaron correctamente.");
  } catch (error) {
    message.textContent = error.message;
    showToast(error.message, true);
  }
});

$("#target-job").addEventListener("change", toggleCustomJobField);

$("#delete-profile").addEventListener("click", async (event) => {
  if (!window.confirm("Se eliminarán el nombre y las preferencias de tu perfil. La cuenta y el resumen de prácticas se conservarán. ¿Continuar?")) return;
  const button = event.currentTarget;
  button.disabled = true;
  try {
    await api("/api/profile", { method: "DELETE" });
    await loadState();
    $("#profile-message").textContent = "Perfil reiniciado. Tu cuenta e historial siguen disponibles.";
    showToast("El perfil se reinició correctamente.");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    button.disabled = false;
  }
});

$("#start-interview").addEventListener("click", () => startInterview());
$("#interview-engine").addEventListener("change", () => updateInterviewAgentCopy());
$("#submit-answer").addEventListener("click", submitAnswer);
$("#timer-toggle").addEventListener("click", toggleTimer);
$("#copy-starter").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("#starter-code").textContent);
    showToast("Plantilla copiada.");
  } catch (error) {
    showToast("No se pudo copiar. Puedes seleccionar el texto de la plantilla.", true);
  }
});
$("#cancel-interview").addEventListener("click", () => {
  resetInterview();
  showToast("La práctica terminó. Puedes volver cuando quieras.");
});
$("#practice-again").addEventListener("click", () => {
  resetInterview();
  startInterview();
});

$("#all-jobs").addEventListener("click", (event) => {
  const practiceButton = event.target.closest("[data-job-practice]");
  if (practiceButton) {
    openView("practice");
    startInterview(practiceButton.dataset.jobPractice);
    return;
  }
  const button = event.target.closest("[data-job-detail]");
  if (!button) return;
  const job = appState.jobs.find((item) => item.id === button.dataset.jobDetail);
  const matched = job.matchedSupports.map((id) => appState.accommodations[id] || id);
  const details = matched.length
    ? `Coincide con estas preferencias de tu perfil: ${matched.join(", ")}.${job.levelMatch ? " También corresponde a tu nivel de experiencia." : " El nivel publicado es distinto al de tu perfil."}`
    : "La vacante comparte algunas características con tu perfil. Revisa sus apoyos y nivel antes de postularte.";
  showToast(details);
});

async function initialize() {
  try {
    const session = await api("/api/me");
    if (session.authenticated) await showApp();
    else {
      showAuth("login");
      $("#login-email").focus();
    }
  } catch (error) {
    showAuth("login");
    showToast(`No se pudo iniciar la aplicación: ${error.message}`, true);
  }
}

initialize();
