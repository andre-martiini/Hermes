# Gemini Model Availability and Preferences (2025)

## Overview
As of early-to-mid 2025, Google has transitioned to the Gemini 2.0 and 2.5 series. The Gemini 1.5 series is considered legacy/unavailable for the current project requirements.

## Current Available Models (Verified February-August 2025)
- **gemini-2.5-flash-lite**: Optimized for speed and cost. This is the model currently prioritized by André Martini for the HERMES bot.
- **gemini-2.5-pro**: High-intelligence model with broad context window and thinking capabilities.
- **gemini-2.5-flash**: Balanced model for general use.
- **gemini-2.0-flash**: The standard stable version of the 2.0 series.
- **gemini-2.0-pro**: Flagship for complex reasoning and large context.
- **gemini-2.0-flash-lite**: Predecessor to the 2.5 lite version.

## Key Operational Knowledge
- **Compatibility**: Flash-Lite models (both 2.0 and 2.5) may have limitations when combining Custom Function Calling with Built-in Google Search tools in specific SDK versions, often leading to `400 INVALID_ARGUMENT`. 
- **Preference**: ALWAYS use the 2.5 series when possible as per user instruction. Avoid referencing 1.5 models.
- **Error Handling**: 
    - `503 UNAVAILABLE`: High demand on the specific lite model. Recommendation: Pause and retry or temporarily switch to its Pro counterpart if urgent.
    - `403 PERMISSION_DENIED (API Leak)`: Ensure keys are stored in `.env` files and never hardcoded in `.py` or `.tsx` files that might be pushed to production or public repositories.

## Storage
- Local `.env` files are used in `Hermes-Bot/` and root directory for key management.
- `.gitignore` must explicitly include `.env` and `.env.local` to prevent leaks.
