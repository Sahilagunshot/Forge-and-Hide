console.log("Forge & Hide JS Loaded");

const heroImage1 = document.getElementById("heroImage1");
const heroImage2 = document.getElementById("heroImage2");

const greenImages = [
    "/static/uploads/green-duffle-side-1.jpg",
    "/static/uploads/green-duffle-side-2.png"
];

const tanImages = [
    "/static/uploads/tan-duffle-side-1.png",
    "/static/uploads/tan-duffle-side-2.png"
];

let greenIndex = 0;
let tanIndex = 0;

setInterval(() => {

    greenIndex++;

    if (greenIndex >= greenImages.length) {
        greenIndex = 0;
    }

    heroImage1.style.opacity = "0";

    setTimeout(() => {
        heroImage1.src = greenImages[greenIndex];
        heroImage1.style.opacity = "1";
    }, 400);

}, 5000);

setInterval(() => {

    tanIndex++;

    if (tanIndex >= tanImages.length) {
        tanIndex = 0;
    }

    heroImage2.style.opacity = "0";

    setTimeout(() => {
        heroImage2.src = tanImages[tanIndex];
        heroImage2.style.opacity = "1";
    }, 400);

}, 5000);