import React, { useState, useEffect, useRef } from 'react';
import { View, FlatList, Dimensions, StatusBar, Alert } from 'react-native';
import VideoItem from '../components/VideoItem';

const { height } = Dimensions.get('window');

const FeedScreen = () => {
    const [videos, setVideos] = useState([]);
    const [activeVideoIndex, setActiveVideoIndex] = useState(0);

    // Mock Data for initial load (simulating API response)
    // In real integration, we fetch from http://localhost:8000/videos/feed
    useEffect(() => {
        const fetchVideos = async () => {
            // Mock data matches our Backend/DB Schema vaguely
            const mockData = [
                {
                    id: '1',
                    video_url: 'https://assets.mixkit.co/videos/preview/mixkit-waves-in-the-water-1164-large.mp4',
                    username: 'ocean_vibe',
                    description: 'Relaxing waves 🌊 #nature',
                    likes: '1.2M',
                    comments: '4K'
                },
                {
                    id: '2',
                    video_url: 'https://assets.mixkit.co/videos/preview/mixkit-tree-with-yellow-flowers-1173-large.mp4',
                    username: 'nature_lover',
                    description: 'Spring is here! 🌸 #flowers',
                    likes: '890K',
                    comments: '2K'
                }
            ];
            setVideos(mockData);
        };
        fetchVideos();
    }, []);

    const onViewableItemsChanged = useRef(({ viewableItems }) => {
        if (viewableItems && viewableItems.length > 0) {
            setActiveVideoIndex(viewableItems[0].index);
        }
    }).current;

    const viewabilityConfig = useRef({
        itemVisiblePercentThreshold: 50
    }).current;

    const handleRemixPress = (item) => {
        Alert.prompt(
            "AI Remix ✨",
            "Enter a prompt to transform this video:",
            [
                {
                    text: "Cancel",
                    style: "cancel"
                },
                {
                    text: "Remix!",
                    onPress: (prompt) => console.log(`Remixing video ${item.id} with prompt: ${prompt}`)
                    // Here we would call the Backend API: POST /remix
                }
            ],
            "plain-text"
        );
    };

    return (
        <View style={{ flex: 1, backgroundColor: 'black' }}>
            <StatusBar barStyle="light-content" />
            <FlatList
                data={videos}
                renderItem={({ item, index }) => (
                    <VideoItem
                        item={item}
                        isActive={activeVideoIndex === index}
                        onRemixPress={handleRemixPress}
                    />
                )}
                keyExtractor={item => item.id}
                pagingEnabled
                vertical
                showsVerticalScrollIndicator={false} // Hide scrollbar for immersion
                snapToInterval={height}
                snapToAlignment={'start'}
                decelerationRate={'fast'}
                viewabilityConfig={viewabilityConfig}
                onViewableItemsChanged={onViewableItemsChanged}
            />
        </View>
    );
};

export default FeedScreen;
