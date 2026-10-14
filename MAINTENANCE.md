# Maintenance policy

- uCore digest updates, Beszel agent digest/patch/minor updates, and GitHub
  Actions digest/patch/minor updates may auto-merge only after required CI succeeds.
- Major updates require human review.
- Secrets never belong in the image or public repository.
- Host-specific configuration belongs in Ignition or Ansible.
- The previous working signed `stable` digest and its immutable tags must remain
  available for rollback.
