"use client";

import { createContext, useContext, useEffect, useState } from "react";

const UserProfileContext = createContext(null);
const KEY = "research-copilot-profile";

const DEFAULT_PROFILE = {
    theme: "dark",
    techStack: [],
    domain: "",
    name: "",
    age: "",
    designation: "",
    education: "",
};

export function UserProfileProvider({ children }) {
    const [profile, setProfile] = useState(DEFAULT_PROFILE);
    const [loaded, setLoaded] = useState(false);

    useEffect(function () {
        try {
            const raw = window.localStorage.getItem(KEY);
            if (raw) {
                setProfile(Object.assign({}, DEFAULT_PROFILE, JSON.parse(raw)));
            }
        } catch (e) {
            // use defaults
        }
        setLoaded(true);
    }, []);

    useEffect(
        function () {
            if (!loaded) return;
            try {
                window.localStorage.setItem(KEY, JSON.stringify(profile));
            } catch (e) {
                // ignore quota errors
            }
            document.documentElement.setAttribute("data-theme", profile.theme);
        },
        [profile, loaded]
    );

    function updateProfile(patch) {
        setProfile(function (prev) {
            return Object.assign({}, prev, patch);
        });
    }

    const value = {
        techStack: profile.techStack,
        domain: profile.domain,
        theme: profile.theme,
        name: profile.name,
        age: profile.age,
        designation: profile.designation,
        education: profile.education,
        updateProfile: updateProfile,
    };

    return <UserProfileContext.Provider value={value}>{children}</UserProfileContext.Provider>;
}

export function useUserProfile() {
    const ctx = useContext(UserProfileContext);
    if (!ctx) {
        throw new Error("useUserProfile must be used within UserProfileProvider");
    }
    return ctx;
}
