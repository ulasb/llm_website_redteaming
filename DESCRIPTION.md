Starting guidance to set up the iterative development process:

Functional Requirements
- User can provide a URL to evaluate
- The system will load the page
- The user can choose a model to use as the agent. This can be any model available through Ollama so these should all be listed for the user to choose from.
- The agent will do four main things:
  1) It will provide feedback on page usability and accessibilitty
  2) Page performance based on loading stats
  3) It will provide feedback on the page code (html, css, js, other accessible artifacts) on performance and best practices
  4) It will provide feedback on potential security issues. This can be things like CVEs, other vulnerabilities that have to do with again the available artifacts or with the server in general.
- Each section will have clear loading signals as they get populated and show status ("Loading data...", "Processing...", etc. using descriptive phrases)
- As the model starts streaming the answers, the section should start getting filled out.

Non-Functional Requirements
- None of the sections take more than five minutes to load
