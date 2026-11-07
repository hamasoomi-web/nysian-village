(() => {
  const toggle = document.getElementById('menuToggle');
  const sidebar = document.getElementById('sidebar');
  if (toggle && sidebar) toggle.addEventListener('click', () => sidebar.classList.toggle('open'));
  document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', () => {
      const button = form.querySelector('button[type="submit"], button:not([type])');
      if (button && !form.action.includes('/toggle') && !form.action.includes('/delete') && !form.action.includes('/pin')) {
        button.dataset.oldText = button.textContent;
        button.classList.add('is-submitting');
      }
    });
  });
  document.querySelectorAll('input[type="range"]').forEach(input => {
    input.addEventListener('input', () => {
      const out = input.parentElement.querySelector('output');
      if (out) out.textContent = input.value + '٪';
    });
  });
})();
