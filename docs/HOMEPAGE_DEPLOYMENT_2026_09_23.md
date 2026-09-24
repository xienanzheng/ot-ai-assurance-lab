# Homepage deployment

Live: https://securecritcticalinfra.dev/

Worker: `secure-critical-infra-home`
Version: `ee5cb51c-c27d-4d37-8c49-ab4c06fff915`

React landing page with local Archivo fonts, interactive water/nuclear/grid scene, mission, approach accordion, illustrative authority gate, actual simulator screenshot and About. All five demo links point to https://ot-aigent-simulation.night-zone.com/.

Verified desktop and mobile rendering, no horizontal overflow at 320/390/768/1440 pixels, sector selection, gate rejection example, mobile menu, demo navigation and image loading. Added Escape handling and favicon. Production returned HTTP 200; navigation reached WaterLab Control Room. Cloudflare analytics initially conflicted with CSP; allowlisted only its script and collector origins, redeployed and verified zero homepage console errors. Impeccable layout detector returned no findings.

This deployment changes the homepage only. Current local RAG and Qwen-performance changes require a separate simulator deployment.

## Desktop refinement deployment

Final version: `71b3c999-5ee2-4475-add2-83542cb24f32`. Live https://securecritcticalinfra.dev/. Revisited LFG at a 1512px viewport. Expanded opening into a continuous desktop canvas, integrated sector selector, strengthened heading weight and enlarged the infrastructure scene. Added pointer and keyboard activation to plant drawings, with explicit transparent hit areas. Preserved reduced-motion support.

Verified 320, 390, 768, 820, 1024, 1512 and 1920px with no document overflow. Two hero columns above 800px, deliberate stacking below. Tested mobile menu, gate rejection example, keyboard plant selection and all three pointer hit areas. Live final build serves `home-DxwzN6FG.js`, its screenshot asset decodes successfully, and browser console reports no errors. Left review browser at 1512px desktop width.
