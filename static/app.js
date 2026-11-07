const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

let appState;
let currentSession = null;
let busy = false;
let toastTimer;

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
  $("#accommodation-options").innerHTML = Object.entries(appState.accommodations).map(([id, label]) => `
    <div class="option">
      <input type="checkbox" id="pref-${id}" name="accommodations" value="${id}"
        ${appState.profile.accommodations.includes(id) ? "checked" : ""}>
      <label for="pref-${id}">${escapeHTML(label)}</label>
    </div>`).join("");
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
  renderJobs(jobs);
  fillProfile();
}

async function loadState() {
  appState = await api("/api/state");
  renderState();
}

function resetInterview() {
  currentSession = null;
  $("#interview-intro").hidden = false;
  $("#question-area").hidden = true;
  $("#interview-finished").hidden = true;
  $("#answer-input").value = "";
  $("#answer-feedback").hidden = true;
}

async function startInterview() {
  const button = $("#start-interview");
  button.disabled = true;
  try {
    const data = await api("/api/interview/start", { method: "POST", body: "{}" });
    currentSession = data.sessionId;
    $("#interview-intro").hidden = true;
    $("#interview-finished").hidden = true;
    $("#question-area").hidden = false;
    showQuestion(data.question);
  } catch (error) {
    showToast(error.message, true);
  } finally {
    button.disabled = false;
  }
}

function showQuestion(question) {
  $("#question-count").textContent = `Pregunta ${question.index + 1} de ${question.total}`;
  $("#progress-bar").setAttribute("aria-valuenow", question.index + 1);
  $("#progress-fill").style.width = `${((question.index + 1) / question.total) * 100}%`;
  $("#question-prompt").textContent = question.prompt;
  const steps = $("#question-steps");
  steps.innerHTML = question.steps.map((step) => `<li>${escapeHTML(step)}</li>`).join("");
  steps.hidden = !question.steps.length;
  $("#answer-input").value = "";
  $("#answer-feedback").hidden = true;
  $("#question-prompt").focus();
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
    const feedback = $("#answer-feedback");
    feedback.textContent = `Gracias por compartirlo. ${data.result.feedback}`;
    feedback.hidden = false;
    if (data.finished) {
      $("#question-area").hidden = true;
      $("#interview-finished").hidden = false;
      $("#finish-summary").textContent = `Tu promedio orientativo fue ${data.summary.average} de 5 en ${data.summary.responses} respuestas.`;
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

$("#start-interview").addEventListener("click", startInterview);
$("#submit-answer").addEventListener("click", submitAnswer);
$("#cancel-interview").addEventListener("click", () => {
  resetInterview();
  showToast("La práctica terminó. Puedes volver cuando quieras.");
});
$("#practice-again").addEventListener("click", () => {
  resetInterview();
  startInterview();
});

$("#all-jobs").addEventListener("click", (event) => {
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
