#### AI-Generated Images (`gen_img_*`)

If the scene outline includes image entries in `mediaGenerations`, use those generated image placeholders for the instructional image elements:

- `src` must be a generated image ID like `"gen_img_1"`, `"gen_img_2"`, etc.
- These placeholders will be replaced with actual generated images after slide creation
- Use the same positioning rules as source images
- Default aspect ratio for generated images: 16:9 (width:height = 16:9)
- For generated images, calculate `height = width / 1.778` unless a different ratio is specified
- Text-to-image spacing: 25-35px vertically and 30-40px horizontally
- Do not emit image elements with empty `src`; use the provided generated image ID or omit the image.
- Keep the image in a bounded visual region. Never make an image span behind body text or cover the footer.
