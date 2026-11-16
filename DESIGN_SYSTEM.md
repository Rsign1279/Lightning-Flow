# LightningFlow 0.4 visual system

An original desktop utility inspired by the simplicity of Wispr Flow's hub, without its branding/assets. No gradients, stock illustrations, emoji icons, fake statistics, subscriptions or accounts.

- Light: warm ivory #FBFAF7, stone sidebar #F2F0EA, white surfaces, charcoal #2B2732, violet #6C4BC3 and a soft lavender #F0EBFA recording panel.
- Dark: warm graphite #19181C, surfaces #222126, lavender #C5B2FA, and #302939 recording panel. Text contrast is preserved in both themes.
- Segoe UI Variable; a restrained 10/11/12/13/14/15/17/21/26 scale, semibold/bold only for navigation, state and hierarchy. Visible keyboard focus remains.
- Original 1.5-point line icons rendered at 4× and cached as light/dark CTkImage pairs. Native window/tray assets use an original violet lightning mark.
- 13–18-pixel surface radii; 8/12/16/22/25 spacing. Most everyday actions are visible without scrolling at the standard window size.
- One primary action, quiet secondary buttons, real shortcut keycaps, local transcript counts and date-grouped logs. Advanced setup moves out of the everyday sidebar.
- Motion remains tied to recording/processing: cached canvas bars, 12-ms attack, 70-ms release, 16-ms render scheduling, rapid opacity transition, Windows reduced-motion support, and no idle animation.

CustomTkinter screen-reader exposure remains limited; this release is not a screen-reader certification. Hold-to-talk and inference code are unchanged from 0.3.1.
