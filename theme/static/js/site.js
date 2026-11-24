// Mobile navigation toggle and image lightbox. The site works without JS.
(function () {
  var nav = document.querySelector(".site-nav");
  var toggle = document.querySelector(".site-nav__toggle");
  if (nav && toggle) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  var box = document.querySelector(".lightbox");
  if (!box || typeof box.showModal !== "function") return;
  var img = box.querySelector("img");
  var cap = box.querySelector(".lightbox__caption");
  var openLink = box.querySelector(".lightbox__open");

  document.querySelectorAll(".gallery__link").forEach(function (a) {
    a.addEventListener("click", function (e) {
      e.preventDefault();
      img.src = a.getAttribute("href");
      img.alt = a.dataset.caption || "";
      cap.textContent = a.dataset.caption || "";
      openLink.href = a.getAttribute("href");
      box.showModal();
    });
  });
  box.querySelector(".lightbox__close").addEventListener("click", function () { box.close(); });
  box.addEventListener("click", function (e) { if (e.target === box) box.close(); });
})();
