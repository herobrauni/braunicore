# Maintenance policy

- uCore digest updates, Beszel digest/patch updates within the selected stable
  release line, and GitHub Actions digest/patch/minor updates may auto-merge
  only after required CI succeeds.
- Major updates and Beszel release-line changes require human review.
- Secrets never belong in the image or public repository.
- Host-specific configuration belongs in Ignition or Ansible.
- The previous working signed `stable` digest and its immutable tags must remain
  available for rollback.
