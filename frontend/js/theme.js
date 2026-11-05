/**
 * SkinSense Theme Controller (Light / Dark Mode)
 */
window.ThemeController = {
  init: function () {
    const savedTheme = localStorage.getItem('skinsense_theme') || 'light';
    this.setTheme(savedTheme);

    const toggleBtn = document.getElementById('theme-toggle-btn');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', () => {
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
        const newTheme = currentTheme === 'light' ? 'dark' : 'light';
        this.setTheme(newTheme);
        Toast.info(`Switched to ${newTheme === 'dark' ? 'Dark' : 'Light'} Mode`, 'Theme Changed');
      });
    }
  },

  setTheme: function (theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('skinsense_theme', theme);

    const icon = document.getElementById('theme-toggle-icon');
    if (icon) {
      if (theme === 'dark') {
        icon.className = 'fa-solid fa-sun';
      } else {
        icon.className = 'fa-solid fa-moon';
      }
    }
  }
};

document.addEventListener('DOMContentLoaded', () => {
  ThemeController.init();
});
