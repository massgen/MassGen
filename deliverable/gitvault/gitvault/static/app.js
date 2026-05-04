document.addEventListener('keydown', (event) => {
  if (event.key === '/' && !['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName)) {
    const search = document.querySelector('input[name="q"]');
    if (search) {
      event.preventDefault();
      search.focus();
    }
  }
});
