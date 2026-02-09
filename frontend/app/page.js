"use client";

import { useState, useRef, useEffect } from "react";
import Image from "next/image";
import { rtdb } from "@/lib/firebase";
import { ref, push, serverTimestamp } from "firebase/database";


// Client-side cache for search results and stream URLs
const searchCache = new Map();
const streamCache = new Map();

export default function Home() {
  const [query, setQuery] = useState("");
  const [songs, setSongs] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [recommendations, setRecommendations] = useState([]);
  const [collections, setCollections] = useState({});
  const [likedSongs, setLikedSongs] = useState(new Set());
  const [current, setCurrent] = useState(null);

  const [loading, setLoading] = useState(false);
  const audioRef = useRef(null);
  const prefetchRef = useRef(null);
  const socketRef = useRef(null);
  const playPromiseRef = useRef(null);

  // Initialize WebSocket connection
  useEffect(() => {
    const connectWS = () => {
      const socket = new WebSocket('wss://sample-backend-production-b1dd.up.railway.app/ws');

      socket.onopen = () => {
        console.log('Connected to SonicStream Real-time Bridge 🔌');
        socketRef.current = socket;
      };

      socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'search_results') {
          // Update cache and songs state instantly
          data.results.forEach(song => {
            if (song.stream_url) streamCache.set(song.id, song.stream_url);
          });
          searchCache.set(data.query.toLowerCase(), data.results);
          setSongs(data.results);
          setLoading(false);
          setSuggestions([]); // Clear suggestions on full search
          if (data.results.length > 0) handleMouseEnter(data.results[0].id);
        } else if (data.type === 'suggestions') {
          if (data.query.toLowerCase() === query.toLowerCase()) {
            setSuggestions(data.results);
          }
        }
      };

      socket.onclose = () => {
        console.log('WebSocket disconnected. Reconnecting...');
        setTimeout(connectWS, 3000); // Auto-reconnect
      };
    };

    connectWS();
    return () => {
      if (socketRef.current) socketRef.current.close();
    };
  }, [query]); // Re-bind on query change to ensure closure has latest query for comparison

  // Debounced autocomplete effect
  useEffect(() => {
    if (query.length < 2) {
      setSuggestions([]);
      return;
    }

    const timer = setTimeout(() => {
      if (socketRef.current?.readyState === WebSocket.OPEN) {
        socketRef.current.send(JSON.stringify({
          type: 'autocomplete',
          query: query
        }));
      }
    }, 300);

    // Fetch collections
    const fetchCollections = async () => {
      try {
        const res = await fetch(`https://sample-backend-production-b1dd.up.railway.app/collections/guest`);
        const data = await res.json();
        if (data.collections) setCollections(data.collections);
      } catch (e) {
        console.error("Failed to fetch collections:", e);
      }
    };
    fetchCollections();

    return () => clearTimeout(timer);
  }, [query]);


  const searchSongs = async () => {
    if (!query) return;

    if (searchCache.has(query.toLowerCase())) {
      const cachedSongs = searchCache.get(query.toLowerCase());
      setSongs(cachedSongs);
      if (cachedSongs.length > 0) handleMouseEnter(cachedSongs[0].id);
      return;
    }

    setLoading(true);

    // Check if WebSocket is ready, else fallback to fetch
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({
        type: 'search',
        query: query
      }));
    } else {
      // Fallback to HTTP if WebSocket isn't live
      try {
        const res = await fetch(`https://sample-backend-production-b1dd.up.railway.app/search?q=${encodeURIComponent(query)}`);
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        const data = await res.json();

        data.forEach(song => {
          if (song.stream_url) streamCache.set(song.id, song.stream_url);
        });

        searchCache.set(query.toLowerCase(), data);
        setSongs(data);
        if (data.length > 0) handleMouseEnter(data[0].id);
      } catch (error) {
        console.error("Search failed:", error);
      } finally {
        setLoading(false);
      }
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === "Enter") {
      searchSongs();
    }
  };

  // Hover-to-Load: Warm up the server cache without downloading data
  const handleMouseEnter = async (songId) => {
    if (current?.id === songId) return;

    try {
      let streamUrl = streamCache.get(songId);
      if (!streamUrl) {
        // Trigger server-side pre-warming/caching (lightweight HEAD request)
        await fetch(`https://sample-backend-production-b1dd.up.railway.app/stream/${encodeURIComponent(songId)}`, { method: 'HEAD' });
      }
      // Note: We no longer set prefetchRef.current.src here to save user data.
      // The HEAD request ensures the server is ready, but no audio bytes are transferred yet.
    } catch (e) {
      console.error("Pre-warm failed", e);
    }
  };


  const handlePlay = async (song) => {
    if (current?.id === song.id && audioRef.current) {
      if (audioRef.current.paused) {
        try {
          playPromiseRef.current = audioRef.current.play();
          await playPromiseRef.current;
        } catch (err) {
          if (err.name !== 'AbortError') console.error("Playback failed:", err);
        }
      } else {
        // Wait for any pending play to finish before pausing
        if (playPromiseRef.current) {
          await playPromiseRef.current.catch(() => { });
        }
        audioRef.current.pause();
      }
      return;
    }

    setCurrent(song);

    if (audioRef.current) {
      const url = `https://sample-backend-production-b1dd.up.railway.app/stream/${encodeURIComponent(song.id)}`;
      audioRef.current.src = url;
      audioRef.current.load();
      try {
        // Log to Firebase Play History
        const historyRef = ref(rtdb, 'play_history/guest'); // Using 'guest' until auth is fully active
        push(historyRef, {
          songId: song.id,
          title: song.title,
          timestamp: serverTimestamp()
        });

        playPromiseRef.current = audioRef.current.play();
        await playPromiseRef.current;

        // Fetch Recommendations for this song
        try {
          const recoRes = await fetch(`https://sample-backend-production-b1dd.up.railway.app/recommend/song/${encodeURIComponent(song.id)}`);
          const recoData = await recoRes.json();
          if (recoData.recommendations) {
            setRecommendations(recoData.recommendations);
          }
        } catch (e) {
          console.error("Failed to fetch recommendations:", e);
        }
      } catch (err) {

        if (err.name !== 'AbortError') {
          console.log("Auto-play blocked or failed:", err);
        }
      }
    }

  };

  const playNext = () => {
    if (!current) return;

    const currentIndex = songs.findIndex(s => s.id === current.id);

    // If we have search results and aren't at the end, play next in list
    if (currentIndex !== -1 && currentIndex < songs.length - 1) {
      handlePlay(songs[currentIndex + 1]);
      return;
    }

    // If we're at the end of search results OR playing a recommendation, play from recommendations (Radio Mode)
    if (recommendations.length > 0) {
      const recoIndex = recommendations.findIndex(s => s.id === current.id);
      const nextReco = recommendations[recoIndex + 1] || recommendations[0];
      handlePlay({ ...nextReco, title: nextReco.name, thumbnail: nextReco.album_image || current.thumbnail });
    } else if (songs.length > 0) {
      handlePlay(songs[0]);
    }
  };

  const playPrevious = () => {
    if (!current || songs.length === 0) return;
    const currentIndex = songs.findIndex(s => s.id === current.id);
    const prevIndex = (currentIndex - 1 + songs.length) % songs.length;
    handlePlay(songs[prevIndex]);
  };

  const toggleLike = (songId) => {
    setLikedSongs(prev => {
      const next = new Set(prev);
      if (next.has(songId)) next.delete(songId);
      else next.add(songId);
      return next;
    });
  };

  // Auto-play next song when current one ends
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const handleEnded = () => playNext();
    audio.addEventListener('ended', handleEnded);
    return () => audio.removeEventListener('ended', handleEnded);
  }, [current, songs, recommendations]);

  return (
    <div className="min-h-screen bg-black text-neutral-400 font-sans selection:bg-purple-500/30 selection:text-purple-200 flex">
      {/* Sidebar */}
      <aside className="hidden lg:flex flex-col w-72 h-screen sticky top-0 bg-black border-r border-white/5 p-6 overflow-y-auto z-40">
        <div className="flex items-center gap-3 mb-10 px-2">
          <div className="w-10 h-10 bg-gradient-to-br from-purple-500 to-blue-600 rounded-xl flex items-center justify-center shadow-[0_0_20px_rgba(168,85,247,0.4)]">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M9 18V5l12-2v13" /><circle cx="6" cy="18" r="3" /><circle cx="18" cy="16" r="3" /></svg>
          </div>
          <span className="text-2xl font-black text-white tracking-tighter uppercase italic">SonicStream</span>
        </div>

        <nav className="space-y-8">
          <div>
            <h5 className="text-[10px] font-bold text-neutral-600 uppercase tracking-widest mb-4 px-2 tracking-widest">Discovery</h5>
            <div className="space-y-1">
              <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl bg-white/5 text-white font-semibold transition-all">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><polyline points="9 22 9 12 15 12 15 22" /></svg>
                Home
              </button>
              <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-white/5 hover:text-neutral-200 transition-all text-sm">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><line x1="2" x2="22" y1="12" y2="12" /><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" /></svg>
                Browse
              </button>
            </div>
          </div>

          <div>
            <h5 className="text-[10px] font-bold text-neutral-600 uppercase tracking-widest mb-4 px-2 tracking-widest">Collections</h5>
            <div className="space-y-1">
              {Object.keys(collections).length > 0 ? Object.entries(collections).map(([id, col]) => (
                <button key={id} className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-white/5 hover:text-neutral-200 transition-all text-xs truncate group text-left">
                  <div className="w-1.5 h-1.5 bg-purple-500 rounded-full group-hover:scale-150 transition-transform flex-shrink-0"></div>
                  {col.name}
                </button>
              )) : (
                <div className="px-3 py-4 bg-white/5 rounded-2xl border border-dashed border-white/5 text-center">
                  <p className="text-[10px] text-neutral-700 italic">No collections yet</p>
                </div>
              )}
            </div>
          </div>
        </nav>
      </aside>

      <div className="flex-grow min-w-0">
        <header className="sticky top-0 z-30 bg-black/60 backdrop-blur-md border-b border-white/5 px-6 py-4">
          <div className="max-w-5xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="relative w-full md:max-w-md group">
              <div className="absolute inset-y-0 left-3 flex items-center pointer-events-none text-neutral-500 group-focus-within:text-purple-500 transition-colors">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" /></svg>
              </div>
              <input
                type="text"
                placeholder="Search tracks, artists, albums..."
                className="w-full bg-neutral-900 border border-white/10 rounded-full py-2.5 pl-10 pr-4 focus:outline-none focus:ring-2 focus:ring-purple-500/50 transition-all font-medium placeholder:text-neutral-600 text-sm"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyPress}
              />
              <button onClick={searchSongs} className="absolute right-1.5 top-1.5 bottom-1.5 px-4 bg-white text-black text-xs font-bold rounded-full hover:bg-neutral-200 active:scale-95 transition-all">
                Search
              </button>
            </div>
          </div>
        </header>

        <main className="max-w-5xl mx-auto p-6 pb-40">
          <div className="grid grid-cols-1 gap-3">
            {songs.map((song) => (
              <div
                key={song.id}
                onClick={() => handlePlay(song)}
                className={`group flex items-center gap-4 p-3 rounded-2xl transition-all border border-transparent ${current?.id === song.id ? "bg-purple-600/10 border-purple-500/20" : "hover:bg-white/5"}`}
              >
                <div className="relative w-14 h-14 flex-shrink-0">
                  <Image src={song.thumbnail} alt="" fill className="object-cover rounded-xl" />
                </div>
                <div className="flex-grow min-w-0">
                  <h4 className="font-bold text-neutral-100 truncate group-hover:text-purple-400 transition-colors italic uppercase tracking-tighter">{song.title}</h4>
                  <p className="text-xs text-neutral-500 mt-1">{(song.duration / 60).toFixed(0)}:{(song.duration % 60).toString().padStart(2, '0')}</p>
                </div>
              </div>
            ))}
          </div>

          {recommendations.length > 0 && (
            <div className="mt-16">
              <div className="flex items-center gap-3 mb-8">
                <div className="w-1.5 h-8 bg-purple-500 rounded-full shadow-[0_0_15px_rgba(168,85,247,0.5)]"></div>
                <h3 className="text-3xl font-black text-white tracking-tighter italic uppercase">More Like This</h3>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6">
                {recommendations.slice(0, 10).map((song) => (
                  <div
                    key={song.id}
                    className="group bg-neutral-900 border border-white/5 p-4 rounded-3xl transition-all hover:scale-[1.03] cursor-pointer"
                    onClick={() => handlePlay({ ...song, title: song.name, thumbnail: song.album_image || current?.thumbnail })}
                  >
                    <div className="relative aspect-square mb-4 overflow-hidden rounded-2xl">
                      <Image src={song.album_image || current?.thumbnail} alt="" fill className="object-cover group-hover:scale-110 transition-transform duration-700" />
                    </div>
                    <h5 className="font-bold text-neutral-100 truncate group-hover:text-purple-400 transition-colors text-sm uppercase tracking-tighter">{song.name}</h5>
                    <p className="text-[10px] text-neutral-500 mt-1 truncate uppercase tracking-widest">{song.artists}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Player Bar */}
      {current && (
        <div className="fixed bottom-6 left-6 right-6 z-50 animate-in fade-in slide-in-from-bottom-5">
          <div className="max-w-5xl mx-auto bg-neutral-900/90 backdrop-blur-2xl border border-white/10 rounded-2xl p-4 shadow-2xl flex flex-col md:flex-row items-center gap-6">
            <div className="flex items-center gap-4 w-full md:w-auto">
              <div className="relative w-14 h-14 flex-shrink-0">
                <Image src={current.thumbnail} alt="" fill className="object-cover rounded-lg" />
              </div>
              <div className="min-w-0 flex-grow md:w-56">
                <h4 className="font-bold text-neutral-100 truncate uppercase tracking-tighter italic">{current.title}</h4>
                <div className="flex items-center gap-2 mt-1">
                  <div className="w-2 h-2 bg-purple-500 rounded-full animate-pulse shadow-[0_0_8px_rgba(168,85,247,0.8)]" />
                  <p className="text-[10px] text-purple-400 font-bold uppercase tracking-widest">Streaming Now</p>
                </div>
              </div>
            </div>

            <div className="flex-grow w-full md:w-auto flex items-center gap-4">
              <button onClick={playPrevious} className="p-2 text-neutral-400 hover:text-white transition-all active:scale-90">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polygon points="19 20 9 12 19 4 19 20" /><line x1="5" x2="5" y1="19" y2="5" /></svg>
              </button>

              <audio ref={audioRef} controls className="w-full h-10 accent-purple-500 filter invert contrast-125" />

              <button onClick={playNext} className="p-2 text-neutral-400 hover:text-white transition-all active:scale-90">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polygon points="5 4 15 12 5 20 5 4" /><line x1="19" x2="19" y1="5" y2="19" /></svg>
              </button>

              <div className="hidden lg:flex items-center gap-4 ml-6 pl-6 border-l border-white/10">
                <button onClick={() => toggleLike(current.id)} className={`p-2 transition-all ${likedSongs.has(current.id) ? 'text-purple-500 scale-125' : 'text-neutral-500 hover:text-white'}`}>
                  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill={likedSongs.has(current.id) ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" /></svg>
                </button>
              </div>
            </div>

            <button onClick={() => setCurrent(null)} className="hidden md:flex p-2 text-neutral-600 hover:text-white transition-colors">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m18 6-12 12m0-12 12 12" /></svg>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
