import { initializeApp, getApps } from "firebase/app";
import { getAuth } from "firebase/auth";
import { getFirestore } from "firebase/firestore";
import { getDatabase } from "firebase/database";

const firebaseConfig = {
    apiKey: "AIzaSyBhVPKAVCnLHdQVSUgcuRxfdcwYj0uO_5M",
    authDomain: "music-app-f2e65.firebaseapp.com",
    databaseURL: "https://music-app-f2e65-default-rtdb.asia-southeast1.firebasedatabase.app",
    projectId: "music-app-f2e65",
    storageBucket: "music-app-f2e65.firebasestorage.app",
    messagingSenderId: "948123881782",
    appId: "1:948123881782:web:546eacb8ca24c6a3602397",
    measurementId: "G-QB5FZ3H9QM"
};

const app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApps()[0];
const auth = getAuth(app);
const db = getFirestore(app);
const rtdb = getDatabase(app);

export { app, auth, db, rtdb };
