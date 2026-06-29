"use client";

import { useState, useEffect } from "react";
import { useUserProfile } from "../../context/UserProfileContext";

const DOMAINS = ["NLP", "Computer Vision", "LLMs", "Reinforcement Learning", "Multimodal", "Other"];

export default function SettingsPage() {
  const profile = useUserProfile();
  const [techStackInput, setTechStackInput] = useState("");

  useEffect(
    function () {
      setTechStackInput(profile.techStack.join(", "));
    },
    [profile.techStack]
  );

  function handleTechStackBlur() {
    const parsed = techStackInput
      .split(",")
      .map(function (s) {
        return s.trim();
      })
      .filter(function (s) {
        return s.length > 0;
      });
    profile.updateProfile({ techStack: parsed });
  }

  return (
    <main className="max-w-2xl mx-auto px-6 py-16">
      <h1 className="font-[var(--font-display)] text-2xl md:text-3xl mb-10">Settings</h1>

      <section className="mb-10">
        <h2 className="text-sm font-medium uppercase tracking-wide text-[var(--text-muted)] mb-4">Appearance</h2>
        <div className="flex gap-3">
          <button
            onClick={function () {
              profile.updateProfile({ theme: "dark" });
            }}
            className={
              "px-4 py-2 rounded-md border text-sm " +
              (profile.theme === "dark" ? "border-[var(--accent)] text-[var(--accent)]" : "border-[var(--border)] text-[var(--text-muted)]")
            }
          >
            Dark
          </button>
          <button
            onClick={function () {
              profile.updateProfile({ theme: "light" });
            }}
            className={
              "px-4 py-2 rounded-md border text-sm " +
              (profile.theme === "light" ? "border-[var(--accent)] text-[var(--accent)]" : "border-[var(--border)] text-[var(--text-muted)]")
            }
          >
            Light
          </button>
        </div>
      </section>

      <section className="mb-10">
        <h2 className="text-sm font-medium uppercase tracking-wide text-[var(--text-muted)] mb-4">Your Tech Stack</h2>
        <input
          type="text"
          value={techStackInput}
          onChange={function (e) {
            setTechStackInput(e.target.value);
          }}
          onBlur={handleTechStackBlur}
          placeholder="e.g. PyTorch, Transformers, Docker"
          className="w-full px-4 py-2.5 rounded-md bg-[var(--surface)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)]"
        />
        <p className="text-xs text-[var(--text-muted)] mt-2">
          Comma-separated. Used to score Tech Stack Match on the Results page.
        </p>
      </section>

      <section className="mb-10">
        <h2 className="text-sm font-medium uppercase tracking-wide text-[var(--text-muted)] mb-4">Domain</h2>
        <select
          value={profile.domain}
          onChange={function (e) {
            profile.updateProfile({ domain: e.target.value });
          }}
          className="w-full px-4 py-2.5 rounded-md bg-[var(--surface)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)]"
        >
          <option value="">Select a domain</option>
          {DOMAINS.map(function (d) {
            return (
              <option key={d} value={d}>
                {d}
              </option>
            );
          })}
        </select>

        {profile.domain === "Other" && (
          <input
            type="text"
            value={profile.customDomain}
            onChange={function (e) {
              profile.updateProfile({ customDomain: e.target.value });
            }}
            placeholder="Enter your domain"
            className="w-full mt-3 px-4 py-2.5 rounded-md bg-[var(--surface)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)]"
          />
        )}
      </section>

      <section>
        <h2 className="text-sm font-medium uppercase tracking-wide text-[var(--text-muted)] mb-4">Profile</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <input
            type="text"
            value={profile.name}
            onChange={function (e) {
              profile.updateProfile({ name: e.target.value });
            }}
            placeholder="Name"
            className="px-4 py-2.5 rounded-md bg-[var(--surface)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)]"
          />
          <input
            type="text"
            value={profile.age}
            onChange={function (e) {
              profile.updateProfile({ age: e.target.value });
            }}
            placeholder="Age"
            className="px-4 py-2.5 rounded-md bg-[var(--surface)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)]"
          />
          <input
            type="text"
            value={profile.designation}
            onChange={function (e) {
              profile.updateProfile({ designation: e.target.value });
            }}
            placeholder="Designation"
            className="px-4 py-2.5 rounded-md bg-[var(--surface)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)]"
          />
          <input
            type="text"
            value={profile.education}
            onChange={function (e) {
              profile.updateProfile({ education: e.target.value });
            }}
            placeholder="Education"
            className="px-4 py-2.5 rounded-md bg-[var(--surface)] border border-[var(--border)] text-sm focus:outline-none focus:border-[var(--accent)]"
          />
        </div>
      </section>
    </main>
  );
}
