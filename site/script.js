/* ============================================
   FaultRay Landing Page Scripts
   ============================================ */

(function () {
  "use strict";

  // --- Navbar scroll effect ---
  var nav = document.getElementById("nav");
  var scrollThreshold = 20;

  function onScroll() {
    if (window.scrollY > scrollThreshold) {
      nav.classList.add("scrolled");
    } else {
      nav.classList.remove("scrolled");
    }
  }

  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  // --- Mobile nav toggle ---
  var navToggle = document.getElementById("nav-toggle");
  var navLinks = document.getElementById("nav-links");

  if (navToggle && navLinks) {
    navToggle.addEventListener("click", function () {
      navToggle.classList.toggle("active");
      navLinks.classList.toggle("open");
    });

    // Close mobile nav when a link is clicked
    var links = navLinks.querySelectorAll("a");
    for (var i = 0; i < links.length; i++) {
      links[i].addEventListener("click", function () {
        navToggle.classList.remove("active");
        navLinks.classList.remove("open");
      });
    }
  }

  // --- Copy buttons ---
  var copyButtons = document.querySelectorAll(".code-copy");

  for (var j = 0; j < copyButtons.length; j++) {
    copyButtons[j].addEventListener("click", function () {
      var btn = this;
      var code = btn.getAttribute("data-code");

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(code).then(function () {
          showCopied(btn);
        });
      } else {
        // Fallback for older browsers
        var textarea = document.createElement("textarea");
        textarea.value = code;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        try {
          document.execCommand("copy");
          showCopied(btn);
        } catch (e) {
          // Silently fail
        }
        document.body.removeChild(textarea);
      }
    });
  }

  function showCopied(btn) {
    var original = btn.textContent;
    btn.textContent = "Copied!";
    btn.classList.add("copied");
    setTimeout(function () {
      btn.textContent = original;
      btn.classList.remove("copied");
    }, 2000);
  }

  // --- Smooth scroll for anchor links (fallback for browsers without CSS scroll-behavior) ---
  var anchorLinks = document.querySelectorAll('a[href^="#"]');
  for (var k = 0; k < anchorLinks.length; k++) {
    anchorLinks[k].addEventListener("click", function (e) {
      var href = this.getAttribute("href");
      if (href === "#") return;

      var target = document.querySelector(href);
      if (target) {
        e.preventDefault();
        var navHeight = nav ? nav.offsetHeight : 0;
        var targetPos = target.getBoundingClientRect().top + window.pageYOffset - navHeight;

        window.scrollTo({
          top: targetPos,
          behavior: "smooth",
        });

        // Update URL without scroll jump
        if (history.pushState) {
          history.pushState(null, null, href);
        }
      }
    });
  }

  // --- Intersection Observer for fade-in animations ---
  if ("IntersectionObserver" in window) {
    var animateElements = document.querySelectorAll(
      ".feature-card, .ps-card, .pricing-card, .quickstart-step, .model-layer, .model-insight-card"
    );

    // Set initial state
    for (var m = 0; m < animateElements.length; m++) {
      animateElements[m].style.opacity = "0";
      animateElements[m].style.transform = "translateY(20px)";
      animateElements[m].style.transition = "opacity 0.5s ease, transform 0.5s ease";
    }

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            // Stagger animation based on position among siblings
            var el = entry.target;
            var parent = el.parentElement;
            var siblings = parent ? parent.children : [];
            var index = 0;
            for (var n = 0; n < siblings.length; n++) {
              if (siblings[n] === el) {
                index = n;
                break;
              }
            }

            setTimeout(function () {
              el.style.opacity = "1";
              el.style.transform = "translateY(0)";
            }, index * 100);

            observer.unobserve(el);
          }
        });
      },
      { threshold: 0.1, rootMargin: "0px 0px -40px 0px" }
    );

    for (var p = 0; p < animateElements.length; p++) {
      observer.observe(animateElements[p]);
    }
  }

  // --- Dashboard bar animation ---
  if ("IntersectionObserver" in window) {
    var barFills = document.querySelectorAll(".dashboard-bar-fill");

    // Set initial width to 0
    for (var q = 0; q < barFills.length; q++) {
      var targetWidth = barFills[q].style.width;
      barFills[q].setAttribute("data-width", targetWidth);
      barFills[q].style.width = "0%";
    }

    var barObserver = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            var bars = entry.target.querySelectorAll(".dashboard-bar-fill");
            bars.forEach(function (bar, idx) {
              setTimeout(function () {
                bar.style.width = bar.getAttribute("data-width");
              }, idx * 200);
            });
            barObserver.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.3 }
    );

    var dashboardBars = document.querySelector(".dashboard-bars");
    if (dashboardBars) {
      barObserver.observe(dashboardBars);
    }
  }

  // --- Terminal restart on click ---
  var terminal = document.querySelector(".terminal");
  if (terminal) {
    terminal.addEventListener("click", function () {
      var lines = terminal.querySelectorAll(".terminal-line");
      var cursor = terminal.querySelector(".terminal-cursor");

      // Reset animations
      for (var r = 0; r < lines.length; r++) {
        lines[r].style.animation = "none";
        lines[r].offsetHeight; // Force reflow
        lines[r].style.animation = "";
      }

      if (cursor) {
        cursor.style.animation = "none";
        cursor.offsetHeight;
        cursor.style.animation = "";
      }
    });
  }
})();
