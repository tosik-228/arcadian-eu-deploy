/**
 * ARCADIAN — site interactions (no framework).
 * Mobile nav toggle + scroll-top button.
 */
(function () {
  "use strict";

  var nav = document.getElementById("site-nav");
  var burger = nav ? nav.querySelector(".nav-burger") : null;
  if (burger) {
    burger.addEventListener("click", function () {
      nav.classList.toggle("nav-open");
    });
    nav.querySelectorAll(".nav-links a").forEach(function (link) {
      link.addEventListener("click", function () {
        nav.classList.remove("nav-open");
      });
    });
  }

  var scrollTop = document.getElementById("scroll-top");
  if (scrollTop) {
    var toggle = function () {
      scrollTop.classList.toggle("active", window.scrollY > 300);
    };
    window.addEventListener("scroll", toggle, { passive: true });
    toggle();
    scrollTop.addEventListener("click", function (event) {
      event.preventDefault();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }
})();
