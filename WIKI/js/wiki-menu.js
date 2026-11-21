(function () {
  'use strict';

  var PANEL_IDS = ['subkultura', 'muzyka', 'diy', 'art'];

  function closeAllPanels() {
    PANEL_IDS.forEach(function (id) {
      var panel = document.getElementById('panel-' + id);
      if (!panel) return;
      panel.classList.remove('open');
      var btn = panel.previousElementSibling;
      if (btn) {
        btn.classList.remove('active');
        btn.setAttribute('aria-expanded', 'false');
      }
    });
  }

  function toggleMenu(menuId) {
    PANEL_IDS.forEach(function (id) {
      var panel = document.getElementById('panel-' + id);
      if (!panel) return;
      var btn = panel.previousElementSibling;
      if (id === menuId) {
        var isOpen = panel.classList.contains('open');
        if (isOpen) {
          panel.classList.remove('open');
          if (btn) {
            btn.classList.remove('active');
            btn.setAttribute('aria-expanded', 'false');
          }
        } else {
          panel.classList.add('open');
          if (btn) {
            btn.classList.add('active');
            btn.setAttribute('aria-expanded', 'true');
          }
        }
      } else {
        panel.classList.remove('open');
        if (btn) {
          btn.classList.remove('active');
          btn.setAttribute('aria-expanded', 'false');
        }
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var buttons = document.querySelectorAll('.menu-btn[data-menu-target]');
    buttons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var target = btn.getAttribute('data-menu-target');
        if (target) {
          toggleMenu(target);
        }
      });
    });

    document.addEventListener('click', function (e) {
      if (!e.target.closest('.menu-item')) {
        closeAllPanels();
      }
    });
  });
})();
