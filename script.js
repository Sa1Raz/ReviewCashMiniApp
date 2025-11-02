let tg = window.Telegram.WebApp;
let user = tg.initDataUnsafe.user;
let userId = user.id;
let role = null;

tg.ready();

async function api(path, data = {}) {
  const res = await fetch(`https://твой-домен.ру/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ userId, ...data })
  });
  return res.json();
}

async function load() {
  const data = await api('get_user');
  role = data.role;
  if (!role) {
    document.getElementById('role-select').classList.remove('hidden');
  } else {
    showMain(data);
  }
}

function chooseRole(r) {
  api('set_role', { role: r }).then(() => location.reload());
}

function showMain(data) {
  document.getElementById('role-select').classList.add('hidden');
  document.getElementById('main').classList.remove('hidden');
  document.getElementById('role-name').innerText = r === 'employer' ? 'Работодатель' : 'Исполнитель';
  document.getElementById('balance').innerText = data.balance.toFixed(2);

  if (r === 'employer') {
    document.getElementById('employer-panel').classList.remove('hidden');
  } else {
    loadTasks();
  }
}

function showCreateTask() {
  document.getElementById('task-form').classList.toggle('hidden');
}

async function createTask() {
  const text = document.getElementById('task-text').value;
  const link = document.getElementById('task-link').value;
  const price = document.getElementById('task-price').value;
  await api('create_task', { text, link, price });
  alert('Задание создано!');
}

async function loadTasks() {
  const tasks = await api('get_tasks');
  const list = document.getElementById('tasks-list');
  list.innerHTML = tasks.map(t => `
    <div class="task-card">
      <p><b>${t.text}</b></p>
      <p>Ссылка: <a href="${t.link}">${t.link}</a></p>
      <p>Цена: ${t.price} ₽</p>
      <button onclick="takeTask(${t.id})">Взять</button>
    </div>
  `).join('');
}

function takeTask(id) {
  api('take_task', { taskId: id }).then(() => {
    alert('Взято! Пришли фото в боте.');
  });
}

function showWithdraw() {
  const amount = prompt('Сумма (мин. 50 ₽):');
  const wallet = prompt('Qiwi кошелёк:');
  if (amount && wallet) {
    api('withdraw', { amount, wallet }).then(() => alert('Заявка отправлена!'));
  }
}

load();