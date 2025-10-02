document.addEventListener('DOMContentLoaded', () => {
    // Intersection Observer for fade-in sections
    const sections = document.querySelectorAll('section');

    const observerOptions = {
        root: null,
        rootMargin: '0px',
        threshold: 0.2 // Trigger when 20% of the section is visible
    };

    const observer = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('is-visible');
                observer.unobserve(entry.target); // Stop observing once visible
            }
        });
    }, observerOptions);

    sections.forEach(section => {
        observer.observe(section);
    });

    // Sticky Header with Shrink Effect
    const mainHeader = document.getElementById('main-header');
    const scrollThreshold = 100; // Distance to scroll before header shrinks

    window.addEventListener('scroll', () => {
        if (window.scrollY > scrollThreshold) {
            mainHeader.classList.add('shrink');
        } else {
            mainHeader.classList.remove('shrink');
        }
    });

    console.log("Bob Dylan website loaded and enhanced!");
});
