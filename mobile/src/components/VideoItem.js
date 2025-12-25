import React, { useRef, useState, useEffect } from 'react';
import { View, Text, StyleSheet, Dimensions, TouchableOpacity, Animated } from 'react-native';
import { Video, ResizeMode } from 'expo-av';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';

const { width, height } = Dimensions.get('window');

const VideoItem = ({ item, isActive, onRemixPress }) => {
    const videoRef = useRef(null);
    const [status, setStatus] = useState({});

    useEffect(() => {
        if (isActive) {
            videoRef.current?.playAsync();
        } else {
            videoRef.current?.pauseAsync();
        }
    }, [isActive]);

    return (
        <View style={styles.container}>
            <Video
                ref={videoRef}
                style={styles.video}
                source={{
                    uri: item.video_url, // URL from our Backend
                }}
                useNativeControls={false}
                resizeMode={ResizeMode.COVER}
                isLooping
                onPlaybackStatusUpdate={status => setStatus(() => status)}
            />

            {/* Dark Gradient Overlay for text readability */}
            <LinearGradient
                colors={['transparent', 'rgba(0,0,0,0.8)']}
                style={styles.gradient}
            />

            {/* Right Side Action Buttons */}
            <View style={styles.rightContainer}>
                <View style={styles.profileContainer}>
                    <Ionicons name="person-circle" size={50} color="white" />
                    <Ionicons name="add-circle" size={24} color="#E94359" style={styles.followIcon} />
                </View>

                <TouchableOpacity style={styles.iconContainer}>
                    <Ionicons name="heart" size={35} color="white" />
                    <Text style={styles.iconLabel}>{item.likes || '12K'}</Text>
                </TouchableOpacity>

                <TouchableOpacity style={styles.iconContainer}>
                    <Ionicons name="chatbubble-ellipses" size={35} color="white" />
                    <Text style={styles.iconLabel}>{item.comments || '450'}</Text>
                </TouchableOpacity>

                {/* THE MAGIC BUTTON: AI REMIX */}
                <TouchableOpacity style={styles.iconContainerRemix} onPress={() => onRemixPress(item)}>
                    <LinearGradient
                        colors={['#A020F0', '#E94359']}
                        style={styles.remixGradient}
                    >
                        <Ionicons name="color-wand" size={30} color="white" />
                    </LinearGradient>
                    <Text style={styles.iconLabel}>Remix</Text>
                </TouchableOpacity>

                <TouchableOpacity style={styles.iconContainer}>
                    <Ionicons name="share-social" size={35} color="white" />
                    <Text style={styles.iconLabel}>Share</Text>
                </TouchableOpacity>
            </View>

            {/* Bottom Info Section */}
            <View style={styles.bottomContainer}>
                <Text style={styles.username}>@{item.username || 'user_gen'}</Text>
                <Text style={styles.description}>{item.description || 'AI Video Magic #viral'}</Text>
                <View style={styles.songRow}>
                    <Ionicons name="musical-notes" size={24} color="white" />
                    <Text style={styles.songName}>Original Sound - AI Beats</Text>
                </View>
            </View>
        </View>
    );
};

const styles = StyleSheet.create({
    container: {
        width: width,
        height: height, // Full Screen
        backgroundColor: 'black',
    },
    video: {
        position: 'absolute',
        top: 0,
        left: 0,
        bottom: 0,
        right: 0,
    },
    gradient: {
        position: 'absolute',
        left: 0,
        right: 0,
        bottom: 0,
        height: 300,
    },
    rightContainer: {
        position: 'absolute',
        right: 10,
        bottom: 100,
        alignItems: 'center',
    },
    profileContainer: {
        marginBottom: 20,
    },
    followIcon: {
        position: 'absolute',
        bottom: -5,
        right: 0
    },
    iconContainer: {
        marginBottom: 20,
        alignItems: 'center',
    },
    iconContainerRemix: {
        marginBottom: 20,
        alignItems: 'center',
    },
    remixGradient: {
        width: 50,
        height: 50,
        borderRadius: 25,
        justifyContent: 'center',
        alignItems: 'center',
        borderWidth: 2,
        borderColor: 'white',
        marginBottom: 5
    },
    iconLabel: {
        color: 'white',
        fontSize: 13,
        fontWeight: '600',
    },
    bottomContainer: {
        position: 'absolute',
        left: 10,
        bottom: 40,
        width: '75%',
    },
    username: {
        color: 'white',
        fontSize: 16,
        fontWeight: '700',
        marginBottom: 5,
    },
    description: {
        color: 'white',
        fontSize: 14,
        marginBottom: 10,
    },
    songRow: {
        flexDirection: 'row',
        alignItems: 'center'
    },
    songName: {
        color: 'white',
        marginLeft: 10,
        fontSize: 14
    }
});

export default VideoItem;
