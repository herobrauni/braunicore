# Maintenance policy

- uCore digest updates and GitHub Actions digest/patch/minor updates may
  auto-merge only after required CI succeeds.
- Every Beszel update requires human provenance review because upstream does
  not sign its images. Release CI mirrors and signs only the reviewed digest.
- Major updates require human review.
- Secrets never belong in the image or public repository.
- Host-specific configuration belongs in Ignition or Ansible.
- The previous working signed `stable` digest and its immutable tags must remain
  available for rollback.
